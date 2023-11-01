import os
import time
import zipfile

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


def handle_dreambooth(params, config):
    # set model params (cjw params.gender(man/woman) fln filan)

    # download image zip from params.s3key (create this)
    # set model training folder to zip output folder.
    # create folder with name params.userId
    # start training

    # Make sure automatic_session is properly defined and initialized
    automatic_session = requests.Session()

    json = {
        "new_model_name": params["userId"],
        "new_model_src": "realisticVisionV51_v51VAE.safetensors [15012c538f]",
    }
    # http://localhost:7860
    # TODO: add source check point and modal type (defaultta varmış)
    response = automatic_session.post(
        url=config.baseurl + "/dreambooth/createModel",
        json=json,
        timeout=config["timeout"],
    )

    if response.status_code != 200:
        print("Error creating model!")
        return

    response = automatic_session.post(
        url=config.baseurl + "/dreambooth/model_config",
        json={
            "model_name": params["userId"],
            "num_train_epochs": 150,
        },
        timeout=config["timeout"],
    )
    if response.status_code != 200:
        print("Error setting model config!")
        return

    # create folder with name params.userId
    user_folder = params["userId"]
    if not os.path.exists(user_folder):
        os.mkdir(user_folder)

    # change working directory to user folder
    os.chdir(user_folder)

    # Download image zip from params.s3key
    s3 = boto3.client("s3")
    zip_file_name = "images.zip"
    s3.download_file(params["s3Url"], zip_file_name)
    # Unzip file
    unzip_folder = "unzipped_images"
    with zipfile.ZipFile(zip_file_name, "r") as zip_ref:
        zip_ref.extractall(unzip_folder)

    # Start training with unzipped folder
    # todo: ADD UNZIPPED FILES TO TRAINING FOLDER
    response = automatic_session.post(
        url=config.baseurl + "/dreambooth/concept",
        json={
            "model_name": params["userId"],
            "instance_dir": os.path.abspath(unzip_folder),
            "instance_token": f"pklb {params['gender']}",
            "class_token": f"photo of a {params['gender']}",
        },
        timeout=config["timeout"],
    )
    if response.status_code != 200:
        print("Error setting concepts!")
        return

    response = automatic_session.post(
        url=config.baseurl + "/dreambooth/startTraining",
        json={
            "model_name": params["userId"],
        },
        timeout=config["timeout"],
    )

    if response.status_code != 200:
        print("Error starting training!")
        return

    time.sleep(600)
    # wait for training to finish check /dreambooth/status check every 5 seconds
    while True:
        response = automatic_session.get(
            url=config.baseurl + "/dreambooth/status",
            timeout=config["timeout"],
        )

        if response.status_code != 200:
            print("Error getting training status!")
            return
        response = response.json()
        if response["active"] == False:
            print("training finished: ", response["last_status"])
            break

        time.sleep(5)

    # send request to /sdapi/v1/txt2img with model name and prompt "photo of a cjw man wearing a suit and tie"
    # loop until we have 100 images
    # upload all images to s3
    # return image urls as string array to backend

    images = []
    while len(images) < 100:
        response = requests.post(
            url=config.baseurl + "/sdapi/v1/txt2img",
            json={
                "model_name": params["userId"],
                "prompt": f"photo of a cjw {params['gender']} wearing a suit and tie",
            },
            timeout=config["timeout"],
        )
        if response.status_code == 200:
            image_url = response.json()["image_url"]
            images.append(image_url)
        else:
            print("Error generating image!")

    uploaded_image_urls = []
    for i, image_url in enumerate(images):
        image_name = f"image_{i}.jpg"
        response = requests.get(image_url)
        with open(image_name, "wb") as f:
            f.write(response.content)
        s3.upload_file(image_name, params["bucket"], image_name)
        uploaded_image_urls.append(f"s3://{params['bucket']}/{image_name}")
        os.remove(image_name)

    return uploaded_image_urls


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
    path = None

    if api_name in config["api"]:
        api_config = config["api"][api_name]
    elif api_name == "dreambooth":
        return handle_dreambooth(params, config)
    else:
        raise Exception("Method '%s' not yet implemented")

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
