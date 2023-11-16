import os
import time

import runpod
import requests
from requests.adapters import HTTPAdapter, Retry
import boto3


automatic_session = requests.Session()
retries = Retry(total=10, backoff_factor=0.1, status_forcelist=[502, 503, 504])
automatic_session.mount("http://", HTTPAdapter(max_retries=retries))


# ---------------------------------------------------------------------------- #
#                              Automatic Functions                             #
# ---------------------------------------------------------------------------- #
def wait_for_service(url):
    """
    Check if the service is ready to receive requests.
    """
    while True:
        try:
            requests.get(url)
            return
        except requests.exceptions.RequestException:
            print("Service not ready yet. Retrying...")
        except Exception as err:
            print("Error: ", err)

        time.sleep(0.2)


def run_inference(params):
    config = {
        "baseurl": "http://127.0.0.1:3000",
        "api": {
            "txt2img": ("POST", "/sdapi/v1/txt2img"),
            "img2img": ("POST", "/sdapi/v1/img2img"),
            "getModels": ("GET", "/sdapi/v1/sd-models"),
            "getOptions": ("GET", "/sdapi/v1/options"),
            "setOptions": ("POST", "/sdapi/v1/options"),
            "getControlnetModels": ("GET", "/controlnet/model_list"),
        },
        "timeout": 600,
    }
    api_name = params["api_name"]

    if api_name in config["api"]:
        api_config = config["api"][api_name]
    else:
        raise Exception("Method '%s' not yet implemented")

    model_s3_key = params["model_s3_key"]
    model_name = model_s3_key.split("/")[-1]

    # check if model exists in /models/Stable-diffusion/<model_name>
    # if not, download from s3
    # if not os.path.exists(
    #     f"/stable-diffusion-webui/models/Stable-diffusion/{model_name}"
    # ):
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
    )
    s3.download_file(
        "photoai-uploads",
        model_s3_key,
        "/stable-diffusion-webui/models/Stable-diffusion/model.ckpt",
    )

    donwloaded_model = os.path.exists(
        "/stable-diffusion-webui/models/Stable-diffusion/model.ckpt"
    )
    if not donwloaded_model:
        raise Exception("Downloaded Model NOT FOUND")

    automatic_session.post(
        url="%s%s" % (config["baseurl"], "/sdapi/v1/refresh-checkpoints"),
        timeout=config["timeout"],
    )

    api_verb = api_config[0]
    api_path = api_config[1]

    response = {}

    if api_verb == "GET":
        response = automatic_session.get(
            url="%s%s" % (config["baseurl"], api_path), timeout=config["timeout"]
        )

    if api_verb == "POST":
        response = automatic_session.post(
            url="%s%s" % (config["baseurl"], api_path),
            json=params,
            timeout=config["timeout"],
        )

    return response.json()


# ---------------------------------------------------------------------------- #
#                                RunPod Handler                                #
# ---------------------------------------------------------------------------- #
def handler(event):
    """
    This is the handler function that will be called by the serverless.
    """

    json = run_inference(event["input"])

    # return the output that you want to be returned like pre-signed URLs to output artifacts
    return json


if __name__ == "__main__":
    wait_for_service(url="http://127.0.0.1:3000/sdapi/v1/txt2img")

    print("WebUI API Service is ready. Starting RunPod...")

    runpod.serverless.start({"handler": handler})
