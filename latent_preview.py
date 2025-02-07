import torch
from PIL import Image, ImageOps
from io import BytesIO
import struct
import numpy as np

from comfy.cli_args import args, LatentPreviewMethod
from comfy.taesd.taesd import TAESD
import folder_paths

MAX_PREVIEW_RESOLUTION = 512

class LatentPreviewer:
    def decode_latent_to_preview(self, x0):
        pass

    def decode_latent_to_preview_image(self, preview_format, x0):
        preview_image = self.decode_latent_to_preview(x0)
        preview_image = ImageOps.contain(preview_image, (MAX_PREVIEW_RESOLUTION, MAX_PREVIEW_RESOLUTION), Image.ANTIALIAS)

        preview_type = 1
        if preview_format == "JPEG":
            preview_type = 1
        elif preview_format == "PNG":
            preview_type = 2

        bytesIO = BytesIO()
        header = struct.pack(">I", preview_type)
        bytesIO.write(header)
        preview_image.save(bytesIO, format=preview_format, quality=95)
        preview_bytes = bytesIO.getvalue()
        return preview_bytes

class TAESDPreviewerImpl(LatentPreviewer):
    def __init__(self, taesd):
        self.taesd = taesd

    def decode_latent_to_preview(self, x0):
        x_sample = self.taesd.decoder(x0)[0].detach()
        # x_sample = self.taesd.unscale_latents(x_sample).div(4).add(0.5)  # returns value in [-2, 2]
        x_sample = x_sample.sub(0.5).mul(2)

        x_sample = torch.clamp((x_sample + 1.0) / 2.0, min=0.0, max=1.0)
        x_sample = 255. * np.moveaxis(x_sample.cpu().numpy(), 0, 2)
        x_sample = x_sample.astype(np.uint8)

        preview_image = Image.fromarray(x_sample)
        return preview_image


class Latent2RGBPreviewer(LatentPreviewer):
    def __init__(self):
        self.latent_rgb_factors = torch.tensor([
                    #   R        G        B
                    [0.298, 0.207, 0.208],  # L1
                    [0.187, 0.286, 0.173],  # L2
                    [-0.158, 0.189, 0.264],  # L3
                    [-0.184, -0.271, -0.473],  # L4
                ], device="cpu")

    def decode_latent_to_preview(self, x0):
        latent_image = x0[0].permute(1, 2, 0).cpu() @ self.latent_rgb_factors

        latents_ubyte = (((latent_image + 1) / 2)
                            .clamp(0, 1)  # change scale from -1..1 to 0..1
                            .mul(0xFF)  # to 0..255
                            .byte()).cpu()

        return Image.fromarray(latents_ubyte.numpy())


def get_previewer(device):
    previewer = None
    method = args.preview_method
    if method != LatentPreviewMethod.NoPreviews:
        # TODO previewer methods
        taesd_decoder_path = folder_paths.get_full_path("vae_approx", "taesd_decoder.pth")

        if method == LatentPreviewMethod.Auto:
            method = LatentPreviewMethod.Latent2RGB
            if taesd_decoder_path:
                method = LatentPreviewMethod.TAESD

        if method == LatentPreviewMethod.TAESD:
            if taesd_decoder_path:
                taesd = TAESD(None, taesd_decoder_path).to(device)
                previewer = TAESDPreviewerImpl(taesd)
            else:
                print("Warning: TAESD previews enabled, but could not find models/vae_approx/taesd_decoder.pth")

        if previewer is None:
            previewer = Latent2RGBPreviewer()
    return previewer


