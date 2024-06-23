# ---------------------------------------------------------------------------- #
#                         Stage 1: Download the models                         #
# ---------------------------------------------------------------------------- #
FROM alpine/git:2.43.0 as download


# ---------------------------------------------------------------------------- #
#                        Stage 3: Build the final image                        #
# ---------------------------------------------------------------------------- #
FROM python:3.10.14-slim as build_final_image
ARG A1111_RELEASE=v1.9.3

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_PREFER_BINARY=1 \
    ROOT=/stable-diffusion-webui \
    PYTHONUNBUFFERED=1

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN export COMMANDLINE_ARGS="--skip-torch-cuda-test --precision full --no-half"
RUN export TORCH_COMMAND='pip install ---no-cache-dir torch==2.1.2+cu118 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118'

RUN apt-get update && \
    apt install -y \
    fonts-dejavu-core rsync git jq moreutils aria2 wget libgoogle-perftools-dev libtcmalloc-minimal4 procps libgl1 libglib2.0-0 && \
    apt-get autoremove -y && rm -rf /var/lib/apt/lists/* && apt-get clean -y

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip

RUN --mount=type=cache,target=/cache --mount=type=cache,target=/root/.cache/pip \
    ${TORCH_COMMAND} && \
    pip install --no-cache-dir xformers==0.0.23.post1 --index-url https://download.pytorch.org/whl/cu118

RUN --mount=type=cache,target=/cache --mount=type=cache,target=/root/.cache/pip \
    pip install onnxruntime-gpu

RUN --mount=type=cache,target=/root/.cache/pip \
    git clone https://github.com/AUTOMATIC1111/stable-diffusion-webui.git && \
    cd stable-diffusion-webui && \
    git reset --hard ${A1111_RELEASE} && \
    python -c "from launch import prepare_environment; prepare_environment()" --skip-torch-cuda-test

# install controlnet
RUN --mount=type=cache,target=/root/.cache/pip \
    git clone https://github.com/Mikubill/sd-webui-controlnet.git stable-diffusion-webui/extensions/sd-webui-controlnet \
    && mkdir -p stable-diffusion-webui/extensions/sd-webui-controlnet/models \
    && pip install -r stable-diffusion-webui/extensions/sd-webui-controlnet/requirements.txt

# install reactor extension
RUN --mount=type=cache,target=/root/.cache/pip \
    git clone https://github.com/Gourieff/sd-webui-reactor.git stable-diffusion-webui/extensions/sd-webui-reactor \
    && pip install -r stable-diffusion-webui/extensions/sd-webui-reactor/requirements.txt

# CyberRealistic_V3.0-FP32.safetensors
ADD ./dreamshaper_8.safetensors /stable-diffusion-webui/models/Stable-diffusion/dreamshaper_8.safetensors
ADD ./realistic_6.safetensors /stable-diffusion-webui/models/Stable-diffusion/realistic_6.safetensors
ADD ./realistic_6.safetensors /model.safetensors
ADD ./control_v11p_sd15_openpose.yaml /stable-diffusion-webui/extensions/sd-webui-controlnet/models/control_v11p_sd15_openpose.yaml
ADD ./control_v11p_sd15_openpose.pth /stable-diffusion-webui/extensions/sd-webui-controlnet/models/control_v11p_sd15_openpose.pth
COPY ./insightface/ /stable-diffusion-webui/models/insightface/

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir runpod opencv-python-headless pyngrok

ADD src .

COPY builder/cache.py /stable-diffusion-webui/cache.py
RUN cd /stable-diffusion-webui && python cache.py --use-cpu=all --ckpt /model.safetensors

RUN chmod +x /start.sh
CMD /start.sh