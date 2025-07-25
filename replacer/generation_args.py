import copy, math
from dataclasses import dataclass
from PIL import Image


@dataclass
class HiresFixArgs:
    upscaler: str
    steps: int
    sampler: str
    scheduler: str
    denoise: float
    cfg_scale: float
    positive_prompt_suffix: str
    size_limit: int
    above_limit_upscaler: str
    unload_detection_models: bool
    disable_cn: bool
    extra_mask_expand: int
    positive_prompt: str
    negative_prompt: str
    sd_model_checkpoint: str
    extra_inpaint_padding: int
    extra_mask_blur: int
    randomize_seed: bool
    soft_inpaint: str
    supersampling: float

DUMMY_HIRESFIX_ARGS = HiresFixArgs("", 0, "", "", 0.0, 0.0, "", 0, "", False, True, 0, "", "", "", 0, 0, False, "Same", 1.0)

@dataclass
class HiresFixCacheData:
    upscaler: str
    generatedImage: Image.Image
    galleryIdx: int


@dataclass
class AppropriateData:
    inputImageIdx: int
    mask: Image.Image
    seed: int


@dataclass
class AnimateDiffArgs:
    fragment_length: int
    internal_fps: float
    batch_size: int
    stride: int
    overlap: int
    latent_power: float
    latent_scale: float
    freeinit_enable: bool
    freeinit_filter: str
    freeinit_ds: float
    freeinit_dt: float
    freeinit_iters: int
    generate_only_first_fragment: bool

    cn_inpainting_model: str
    control_weight: float
    force_override_sd_model: bool
    force_sd_model_checkpoint: str
    motion_model: str

    needApplyAnimateDiff: bool = False
    needApplyCNForAnimateDiff: bool = False
    video_path: str = None
    mask_path: str = None

DUMMY_ANIMATEDIFF_ARGS = AnimateDiffArgs(0, 0, 0, 0, 0, 0, 0, False, "", 0, 0, 0, False, "", 0, False, "", "")

@dataclass
class GenerationArgs:
    positivePrompt: str
    negativePrompt: str
    detectionPrompt: str
    avoidancePrompt: str
    upscalerForImg2Img: str
    seed: int
    samModel: str
    grdinoModel: str
    boxThreshold: float
    maskExpand: int
    maxResolutionOnDetection: int
    steps: int
    sampler_name: str
    scheduler: str
    mask_blur: int
    inpainting_fill: int
    batch_count: int
    batch_size: int
    cfg_scale: float
    denoising_strength: float
    height: int
    width: int
    inpaint_full_res_padding: int
    img2img_fix_steps: bool
    inpainting_mask_invert : int
    images: list[Image.Image]
    override_sd_model: bool
    sd_model_checkpoint: str
    mask_num: int
    avoidance_mask: Image.Image
    only_custom_mask: bool
    custom_mask: Image.Image
    use_inpaint_diff: bool
    clip_skip: int

    pass_into_hires_fix_automatically: bool
    save_before_hires_fix: bool
    do_not_use_mask: bool
    rotation_fix: str
    variation_seed: int
    variation_strength: float
    integer_only_masked: bool
    forbid_too_small_crop_region: bool
    correct_aspect_ratio: bool

    hires_fix_args: HiresFixArgs
    cn_args: list
    soft_inpaint_args: list

    mask: Image.Image = None
    mask_num_for_metadata: int = None
    hiresFixCacheData: HiresFixCacheData = None
    addHiresFixIntoMetadata: bool = False
    appropriateInputImageDataList: list[AppropriateData] = None
    originalW = None
    originalH = None
    previous_frame_into_controlnet: list[str] = None
    animatediff_args: AnimateDiffArgs = None

    def totalSteps(self):
        total = min(math.ceil((self.steps-1) * (1 if self.img2img_fix_steps else self.denoising_strength) + 1), self.steps)
        if self.animatediff_args and self.animatediff_args.freeinit_enable:
            total *= self.animatediff_args.freeinit_iters
        return total

    def copy(self):
        gArgs = copy.copy(self)
        gArgs.cn_args = copy.copy(list(gArgs.cn_args))
        for i in range(len(gArgs.cn_args)):
            gArgs.cn_args[i] = gArgs.cn_args[i].copy()
        gArgs.animatediff_args = copy.copy(gArgs.animatediff_args)
        gArgs.soft_inpaint_args = copy.copy(gArgs.soft_inpaint_args)
        gArgs.hires_fix_args = copy.copy(gArgs.hires_fix_args)
        gArgs.images = copy.copy(gArgs.images)
        for i in range(len(gArgs.images)):
            gArgs.images[i] = gArgs.images[i].copy()
        gArgs.mask = copy.copy(gArgs.mask)
        gArgs.hiresFixCacheData = copy.copy(gArgs.hiresFixCacheData)
        if gArgs.appropriateInputImageDataList is not None:
            gArgs.appropriateInputImageDataList = copy.copy(gArgs.appropriateInputImageDataList)
            for i in range(len(gArgs.appropriateInputImageDataList)):
                gArgs.appropriateInputImageDataList[i] = gArgs.appropriateInputImageDataList[i].copy()
        return gArgs
