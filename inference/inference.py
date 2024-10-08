import base64
import logging
from io import BytesIO
from PIL import Image

import torch
from diffusers import StableVideoDiffusionPipeline
from diffusers.utils import load_image


logger = logging.getLogger(__name__)

BASE64_PREFIX = "data:text/plain;base64,"

def model_fn(model_dir):
    logger.info(f"model_dir: {model_dir}")
    pipe = StableVideoDiffusionPipeline.from_pretrained(
        model_dir,
        torch_dtype=torch.float16,
        variant="fp16",
        use_safetensors=True,
    )
    pipe.enable_model_cpu_offload()

    return pipe


def predict_fn(data, pipe):
    # get image and inference parameters
    # https://github.com/huggingface/diffusers/blob/ae05050db9d37d5af48a6cd0d6510a5ffb1c1cd4/src/diffusers/pipelines/stable_video_diffusion/pipeline_stable_video_diffusion.py#L339
    movie_title = data.pop("movie_title")
    image = data.pop("image")
    width = data.pop("width", 1024)
    height = data.pop("height", 576)
    num_frames = data.pop("num_frames", 25)
    num_inference_steps = data.pop("num_inference_steps", 25)
    min_guidance_scale = data.pop("min_guidance_scale", 1.0)
    max_guidance_scale = data.pop("max_guidance_scale", 3.0)
    fps = data.pop("fps", 6)
    motion_bucket_id = data.pop("motion_bucket_id", 127)
    noise_aug_strength = data.pop("noise_aug_strength", 0.02)
    decode_chunk_size = data.pop("decode_chunk_size", 8)
    seed = data.pop("seed", 42)

    if image.startswith(BASE64_PREFIX):
        # load image from base64-encoded data URI
        image = image.removeprefix(BASE64_PREFIX)
        with BytesIO(base64.b64decode(image)) as buffered:
            image = Image.open(buffered).copy()
    else:
        # load image from URL
        image = load_image(image).copy()

    image.thumbnail((width, height), Image.Resampling.LANCZOS)

    generator = torch.manual_seed(seed)

    # invoke model
    frames = pipe(
        image,
        width=image.width,
        height=image.height,
        num_frames=num_frames,
        num_inference_steps=num_inference_steps,
        min_guidance_scale=min_guidance_scale,
        max_guidance_scale=max_guidance_scale,
        fps=fps,
        motion_bucket_id=motion_bucket_id,
        noise_aug_strength=noise_aug_strength,
        decode_chunk_size=decode_chunk_size,
        generator=generator,
    ).frames[0]

    # create response
    encoded_frames = []
    for frame in frames:
        with BytesIO() as buffered:
            frame.save(buffered, format="JPEG", quality=95, subsampling=0)
            encoded_frames.append(base64.b64encode(buffered.getvalue()).decode())

    # return response
    return {
        "frames": encoded_frames,
        "config": {
            "movie_title": movie_title,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "num_inference_steps": num_inference_steps,
            "min_guidance_scale": min_guidance_scale,
            "max_guidance_scale": max_guidance_scale,
            "fps": fps,
            "motion_bucket_id": motion_bucket_id,
            "noise_aug_strength": noise_aug_strength,
            "decode_chunk_size": decode_chunk_size,
            "seed": seed,
        }
    }
