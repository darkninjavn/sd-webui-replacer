import subprocess
import cv2
import os
import modules.shared as shared
from PIL import Image
from shutil import rmtree
from replacer.generation_args import GenerationArgs
try:
    from imageio_ffmpeg import get_ffmpeg_exe
    FFMPEG = get_ffmpeg_exe()
except Exception as e:
    FFMPEG = 'ffmpeg'


def runFFMPEG(*ffmpeg_cmd):
    ffmpeg_cmd = [FFMPEG] + list(ffmpeg_cmd)
    print(' '.join(f"'{str(v)}'" if ' ' in str(v) else str(v) for v in ffmpeg_cmd))
    rc = subprocess.run(ffmpeg_cmd).returncode
    if rc != 0:
        raise Exception(f'ffmpeg exited with code {rc}. See console for details')



def separate_video_into_frames(video_path, fps_out, out_path, ext):
    assert video_path, 'video not selected'
    assert out_path, 'out path not specified'

    # Create the temporary folder if it doesn't exist
    os.makedirs(out_path, exist_ok=True)

    # Open the video file
    assert fps_out != 0, "fps can't be 0"

    runFFMPEG(
        '-i', video_path,
        '-vf', f'fps={fps_out}',
        '-y',
        os.path.join(out_path, f'frame_%05d.{ext}'),
    )


def readImages(input_dir):
    assert input_dir, 'input directory not selected'
    image_list = shared.listfiles(input_dir)
    for filename in image_list:
        try:
            image = Image.open(filename)
        except Exception:
            continue
        yield image


def getVideoFrames(video_path, fps):
    assert video_path, 'video not selected'
    temp_folder = os.path.join(os.path.dirname(video_path), 'temp')
    if os.path.exists(temp_folder):
        rmtree(temp_folder)
    fps_in, fps_out = separate_video_into_frames(video_path, fps, temp_folder)
    return readImages(temp_folder), fps_in, fps_out


def save_video(frames_dir, fps, org_video, output_path, seed):
    runFFMPEG(
        '-framerate', str(fps),
        '-i', os.path.join(frames_dir, f'%5d-{seed}.{shared.opts.samples_format}'),
        '-r', str(fps),
        '-i', org_video,
        '-map', '0:v:0',
        '-map', '1:a:0?',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-vf', f'fps={fps}',
        '-profile:v', 'main',
        '-pix_fmt', 'yuv420p',
        '-shortest',
        '-y',
        output_path
    )


def fastFrameSave(image: Image.Image, path: str, idx):
    savePath = os.path.join(path, f'frame_{idx}.{shared.opts.samples_format}')
    image.convert('RGB').save(savePath, subsampling=0, quality=93)


def overrideSettingsForVideo():
    old_samples_filename_pattern = shared.opts.samples_filename_pattern
    old_save_images_add_number = shared.opts.save_images_add_number
    old_controlnet_ignore_noninpaint_mask = shared.opts.data.get("controlnet_ignore_noninpaint_mask", False)
    def restoreOpts():
        shared.opts.samples_filename_pattern = old_samples_filename_pattern
        shared.opts.save_images_add_number = old_save_images_add_number
        shared.opts.data["controlnet_ignore_noninpaint_mask"] = old_controlnet_ignore_noninpaint_mask
    shared.opts.samples_filename_pattern = "[seed]"
    shared.opts.save_images_add_number = True
    shared.opts.data["controlnet_ignore_noninpaint_mask"] = True
    return restoreOpts



def getFpsFromVideo(video_path: str) -> float:
    video = cv2.VideoCapture(video_path)
    fps = video.get(cv2.CAP_PROP_FPS)
    video.release()
    return fps

FREEINIT_filter_type_list = [
    "butterworth",
    "gaussian",
    "box",
    "ideal"
]
