import os, copy, math, shutil
from PIL import Image, ImageChops
from tqdm import tqdm
from modules import shared, errors
from replacer.generation_args import GenerationArgs
from replacer.mask_creator import createMask, NothingDetectedError
from replacer.inpaint import inpaint
from replacer.generate import generateSingle
from replacer.tools import ( interrupted, applyMaskBlur, clearCache, applyRotationFix, removeRotationFix,
    Pause, extraMaskExpand,
)
from replacer.video_tools import fastFrameSave
from replacer.extensions import replacer_extensions



def processFragment(fragmentPath: str, initImage: Image.Image, gArgs: GenerationArgs):
    initImage = applyRotationFix(initImage, gArgs.rotation_fix)
    fastFrameSave(initImage, os.path.join(fragmentPath, 'frames'), 0)
    gArgs = gArgs.copy()
    gArgs.inpainting_mask_invert = False
    gArgs.mask_blur = 0
    gArgs.animatediff_args.needApplyAnimateDiff = True
    gArgs.animatediff_args.video_path = os.path.join(fragmentPath, 'frames')
    gArgs.animatediff_args.mask_path = os.path.join(fragmentPath, 'masks')
    processed, _ = inpaint(initImage, gArgs)

    outDir = os.path.join(fragmentPath, 'out')
    for idx in range(len(processed.images)):
        fastFrameSave(processed.images[idx], outDir, idx)

    return processed


def detectVideoMasks(gArgs: GenerationArgs, frames: list[Image.Image], masksPath: str, maxNum: int|None) -> None:
    blackFilling = Image.new('L', frames[0].size, 0).convert('RGBA')
    if not maxNum:
        maxNum = len(frames)
    mask = None
    shared.state.job_count = maxNum
    Pause.paused = False

    for idx in range(maxNum):
        Pause.wait()
        if interrupted(): return
        shared.state.textinfo = f"generating mask {idx+1} / {maxNum}"
        print(f"    {idx+1} / {maxNum}")

        frame = frames[idx].convert('RGBA')
        try:
            mask = createMask(frame, gArgs).mask
            if gArgs.inpainting_mask_invert:
                mask = ImageChops.invert(mask.convert('L'))
            mask = applyMaskBlur(mask.convert('RGBA'), gArgs.mask_blur)
            mask = mask.resize(frame.size)
        except NothingDetectedError as e:
            print(e)
            if mask is None or mask is blackFilling:
                mask = blackFilling
            else:
                mask = extraMaskExpand(mask, 50)

        fastFrameSave(mask, masksPath, idx)
        shared.state.nextjob()



def getFragments(gArgs: GenerationArgs, fragments_path: str, frames: list[Image.Image], masks: list[Image.Image], totalFragments: int):
    fragmentSize = gArgs.animatediff_args.fragment_length

    fragmentNum = 0
    frameInFragmentIdx = fragmentSize
    fragmentPath: str = None
    framesDir: str = None
    masksDir: str = None
    outDir: str = None
    frame: Image.Image = None
    mask: Image.Image = None


    for frameIdx in range(len(masks)):
        if frameInFragmentIdx == fragmentSize:
            if fragmentPath is not None:
                text = f"inpainting fragment {fragmentNum} / {totalFragments}"
                print(text)
                shared.state.textinfo = text
                yield fragmentPath
            frameInFragmentIdx = 0
            fragmentNum += 1
            fragmentPath = os.path.join(fragments_path, f"fragment_{fragmentNum}")

            framesDir = os.path.join(fragmentPath, 'frames'); os.makedirs(framesDir, exist_ok=True)
            masksDir = os.path.join(fragmentPath, 'masks'); os.makedirs(masksDir, exist_ok=True)
            outDir = os.path.join(fragmentPath, 'out'); os.makedirs(outDir, exist_ok=True)

            # last frame goes first in the next fragment
            if mask is not None:
                fastFrameSave(frame, framesDir, frameInFragmentIdx)
                fastFrameSave(mask, masksDir, frameInFragmentIdx)
                frameInFragmentIdx = 1

        Pause.wait()
        if interrupted(): return
        print(f"    Preparing frame in fragment {fragmentNum}: {frameInFragmentIdx+1} / {fragmentSize}")

        frame = frames[frameIdx]
        mask = masks[frameIdx]

        frame = applyRotationFix(frame, gArgs.rotation_fix)
        fastFrameSave(frame, framesDir, frameInFragmentIdx)
        mask = applyRotationFix(mask, gArgs.rotation_fix)
        fastFrameSave(mask, masksDir, frameInFragmentIdx)
        frameInFragmentIdx += 1

    if frameInFragmentIdx > 1:
        for idx in range(frameInFragmentIdx+1, min(fragmentSize, 12)):
            fastFrameSave(frame, framesDir, idx)
            fastFrameSave(mask, masksDir, idx)

        text = f"inpainting fragment {fragmentNum} / {totalFragments}"
        print(text)
        shared.state.textinfo = text
        yield fragmentPath


def animatediffGenerate(gArgs: GenerationArgs, fragments_path: str, result_dir: str,
                            frames: list[Image.Image], masks: list[Image.Image], video_fps: float):
    if gArgs.animatediff_args.force_override_sd_model:
        gArgs.override_sd_model = True
        gArgs.sd_model_checkpoint = gArgs.animatediff_args.force_sd_model_checkpoint
    if gArgs.animatediff_args.internal_fps <= 0:
        gArgs.animatediff_args.internal_fps = video_fps
    if gArgs.animatediff_args.fragment_length <= 0 or len(masks) < gArgs.animatediff_args.fragment_length:
        gArgs.animatediff_args.fragment_length = len(masks)
    gArgs.animatediff_args.needApplyCNForAnimateDiff = True

    totalFragments = math.ceil((len(masks) - 1) / (gArgs.animatediff_args.fragment_length - 1))
    if gArgs.animatediff_args.generate_only_first_fragment:
        totalFragments = 1

    try:
        shared.state.textinfo = f"processing the first frame. Total fragments number = {totalFragments}"
        firstFrameGArgs = gArgs.copy()
        firstFrameGArgs.only_custom_mask = True
        firstFrameGArgs.custom_mask = masks[0]
        processedFirstImg, _ = generateSingle(frames[0], firstFrameGArgs, "", "", False, [], None)
        initImage: Image.Image = processedFirstImg.images[0]
    except NothingDetectedError as e:
        print(e)
        initImage: Image.Image = copy.copy(frames[0])

    oldJob = shared.state.job
    shared.state.end()
    shared.state.begin(oldJob + '_animatediff_inpaint')
    shared.state.job_count = totalFragments
    shared.total_tqdm.clear()
    shared.total_tqdm.updateTotal(totalFragments * gArgs.totalSteps())
    Pause.paused = False

    fragmentPaths = []

    try:
        for fragmentPath in getFragments(gArgs, fragments_path, frames, masks, totalFragments):
            if not shared.cmd_opts.lowram: # do not confuse with lowvram. lowram is for really crazy people
                clearCache()
            processed = processFragment(fragmentPath, initImage, gArgs)
            fragmentPaths.append(fragmentPath)
            initImage = processed.images[-1]
            if gArgs.animatediff_args.generate_only_first_fragment:
                break
            if interrupted():
                break
    except Exception as e:
        if type(e) is replacer_extensions.controlnet.UnitIsReserved:
            raise
        errors.report(f'{e} ***', exc_info=True)


    text = "merging fragments"
    shared.state.textinfo = text
    print(text)
    def readImages(input_dir: str):
        image_list = shared.listfiles(input_dir)
        for filepath in image_list:
            image = Image.open(filepath).convert('RGBA')
            image.original_path = filepath
            yield image
    def saveImage(image: Image.Image):
        if not image: return
        savePath = os.path.join(result_dir, f"{frameNum:05d}-{gArgs.seed}.{shared.opts.samples_format}")
        if hasattr(image, 'original_path') and image.original_path:
            shutil.copy(image.original_path, savePath)
        else:
            image.convert('RGB').save(savePath)
    os.makedirs(result_dir, exist_ok=True)
    theLastImage = None
    frameNum = 0

    for fragmentPath in tqdm(fragmentPaths):
        images = list(readImages(os.path.join(fragmentPath, 'out')))
        if len(images) <= 1:
            break
        if theLastImage:
            images[0] = Image.blend(images[0], theLastImage, 0.5)
        theLastImage = images[-1]
        images = images[:-1]

        for image in images:
            if frameNum >= len(masks):
                break
            saveImage(image)
            frameNum += 1
    saveImage(theLastImage)


