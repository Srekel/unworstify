import filecmp
import json
import math
import os
import shutil
import subprocess
import time
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont


class Input:
    def __init__(self):
        self.areas = {}


class Area:
    def __init__(self):
        pass


class Stamp:
    def __init__(self):
        pass


def load_inputs(base_path, settings):
    inputs = {}
    for input in settings["inputs"]:
        inp = Input()
        inp.name = input["name"]
        inp.file = os.path.join(base_path, input["file"])
        for area in input["focus_areas"]:
            ar = Area()
            ar.name = area["name"]
            ar.focus_top_left = (area["area"][0], area["area"][1])
            ar.focus_bottom_right = (area["area"][2], area["area"][3])
            ar.size_x = ar.focus_bottom_right[0] - ar.focus_top_left[0]
            ar.size_y = ar.focus_bottom_right[1] - ar.focus_top_left[1]
            ar.focus_center_x = ar.focus_top_left[0] + ar.size_x / 2
            ar.focus_center_y = ar.focus_top_left[1] + ar.size_y / 2
            inp.areas[ar.name] = ar
        inputs[inp.name] = inp

        print("Outputting debug image for ", inp.name)
        resize_factor = 1
        im = Image.open(inp.file)
        size_in_x, size_in_y = im.size
        im = im.resize(
            (size_in_x // resize_factor,
             size_in_y // resize_factor)).convert('L').convert('RGB')
        im = im.filter(ImageFilter.GaussianBlur(radius=2))
        size_in_x, size_in_y = im.size
        center_x, center_y = size_in_x // 2, size_in_y // 2
        draw = ImageDraw.Draw(im)
        draw.line(
            [(center_x - 10, center_y - 10), (center_x + 10, center_y + 10)],
            fill=(255, 0, 0, 255))
        draw.line(
            [(center_x - 10, center_y + 10), (center_x + 10, center_y - 10)],
            fill=(255, 0, 0, 255))
        draw.line(
            [(center_x - 10, center_y - 11), (center_x + 10, center_y + 9)],
            fill=(0, 0, 0, 255))
        draw.line(
            [(center_x - 10, center_y + 9), (center_x + 10, center_y - 11)],
            fill=(0, 0, 0, 255))

        colors = [(100, 255, 0, 255), (0, 100, 255, 255), (255, 255, 0, 255)]
        color_index = 0

        for aname, area in inp.areas.items():
            center_x = area.focus_center_x // resize_factor
            center_y = area.focus_center_y // resize_factor
            size_x = (area.size_x // resize_factor) // 2
            size_y = (area.size_y // resize_factor) // 2
            draw.line(
                [(center_x - 10, center_y - 10),
                 (center_x - 10, center_y + 10),
                 (center_x + 10, center_y + 10),
                 (center_x + 10, center_y - 10),
                 (center_x - 10, center_y - 10)],
                fill=colors[color_index])

            draw.line(
                [(center_x - size_x, center_y - size_y),
                 (center_x - size_x, center_y + size_y),
                 (center_x + size_x, center_y + size_y),
                 (center_x + size_x, center_y - size_y),
                 (center_x - size_x, center_y - size_y)],
                fill=colors[color_index])

            iterations = 4 + color_index
            for i in range(-iterations + 1, iterations):
                if i == 0: continue
                draw.line(
                    [(center_x + i * size_x / iterations,
                      center_y - size_y / 4),
                     (center_x + i * size_x / iterations,
                      center_y + size_y / 4)],
                    fill=colors[color_index])
                draw.line(
                    [(center_x - size_x / 4,
                      center_y + i * size_y / iterations),
                     (center_x + size_x / 4,
                      center_y + i * size_y / iterations)],
                    fill=colors[color_index])

            color_index += 1

        im.save(inp.name + "_debug.png")
    return inputs


def load_stamps(base_path, settings):
    stamps = {}
    for stamp in settings["stamps"]:
        st = Stamp()
        st.name = stamp["name"]
        st.position = stamp["position"]
        if 0 <= st.position[1] <= 1:
            st.position = (st.position[0], 1 - st.position[1])
        else:
            st.position = (int(st.position[0]), int(st.position[1]))
        st.scale_x = 1
        if "scale_x" in stamp:
            st.scale_x = stamp["scale_x"]
        if "image" in stamp:
            st.image = os.path.join(base_path, stamp["image"])
        if "text" in stamp:
            st.text = stamp["text"]
            st.font = stamp["font"]
            st.font_size = stamp["font_size"]
            st.color = tuple(stamp["text_color"])
        stamps[st.name] = st
    return stamps


def apply_focus(im, area, conv):
    size_in_x, size_in_y = im.size
    in_aspect = size_in_x / size_in_y

    size_out_x = size_in_x
    if "size_x" in conv:
        size_out_x = conv["size_x"]

    if "size_y" in conv:
        size_out_y = conv["size_y"]
    else:
        size_out_y = int(size_out_x / in_aspect)

    out_aspect = size_out_x / size_out_y
    print("Aspect in:    ", in_aspect)
    print("Aspect out:   ", out_aspect)

    # Resize to encompass whole output
    focus_ratio_x = area.size_x / size_in_x
    focus_ratio_y = area.size_y / size_in_y

    focus_size_out_x = size_out_x * focus_ratio_x
    focus_size_out_y = size_out_y * focus_ratio_y
    snugness_x = size_out_x / focus_size_out_x
    snugness_y = size_out_y / focus_size_out_y
    if snugness_x < snugness_y:
        print("Y snugness")
        size_resized_x = int(size_out_x / focus_ratio_x)
        size_resized_y = int(size_resized_x / in_aspect)
    else:
        # Tighter fit on x-axis than y-axis
        print("X snugness")
        size_resized_y = int(size_out_y / focus_ratio_y)
        size_resized_x = int(size_resized_y * in_aspect)

    resize_filter = Image.BICUBIC
    filter_name = "BICUBIC"
    if "filter" in conv:
        filter_name = conv["filter"]
    if filter_name == "LANCZOS":
        resize_filter = Image.LANCZOS
    elif filter_name == "HAMMING":
        resize_filter = Image.HAMMING
    im = im.resize((size_resized_x, size_resized_y), resize_filter)
    print("Size in:      ", size_in_x, size_in_y)
    print("Size out:     ", size_out_x, size_out_y)
    print("Size resized: ", size_resized_x, size_resized_y)
    print("Focus ratio:   %.0f%%, %.0f%%" % (100 * focus_ratio_x,
                                             100 * focus_ratio_y))
    # out_filename = out_filename_base + "_resized.png"
    # im.save(out_filename)

    # Crop to final size
    resized_center_x = size_resized_x * (area.focus_center_x / size_in_x)
    resized_center_y = size_resized_y * (area.focus_center_y / size_in_y)
    cropbox = [
        int(resized_center_x - size_out_x / 2),
        int(resized_center_y - size_out_y / 2),
        123456,
        123456,
    ]
    if cropbox[0] < 0:
        print("OUT OF BOUNDS A BIT, adjusting x by", cropbox[0])
        cropbox[0] = 0
    if cropbox[1] < 0:
        print("OUT OF BOUNDS A BIT, adjusting y by", cropbox[1])
        cropbox[1] = 0

    cropbox[2] = cropbox[0] + size_out_x
    cropbox[3] = cropbox[1] + size_out_y

    if cropbox[2] > size_out_x:
        print("OUT OF BOUNDS A BIT x by ", cropbox[2] - size_out_x)
    if cropbox[3] > size_out_y:
        print("OUT OF BOUNDS A BIT y by ", cropbox[3] - size_out_y)

    print("Crop center:  ", resized_center_x, resized_center_y)
    # print("Crop size:   ", cropbox[2] - cropbox[0],
    #       cropbox[3] - cropbox[1])
    print("Crop box:      (%d, %d), (%d, %d) " % (cropbox[0], cropbox[1],
                                                  cropbox[2], cropbox[3]))
    im = im.crop(cropbox)
    return im


def apply_vignette(im):
    size_x, size_y = im.size
    im = im.convert("RGBA")
    pixels = im.load()
    factor = 40

    for y in range(size_y):
        for x in range(size_x):
            uv_x = x / size_x
            uv_y = y / size_y
            uv_x2 = uv_x * (1 - uv_y)
            uv_y2 = uv_y * (1 - uv_x)
            vig = uv_x2 * uv_y2 * factor

            vig = math.pow(vig, 0.15)
            vig = min(1, vig)
            r, g, b, a = pixels[x, y]
            pixels[x, y] = int(r * vig), int(g * vig), int(b * vig), int(a)
    return im


def apply_stamp_image(im, stamp):
    size_x, size_y = im.size
    tim = im.convert("RGBA")
    stamp_im = Image.open(stamp.image).convert("RGBA")
    stamp_size_x, stamp_size_y = stamp_im.size
    if isinstance(stamp.position[0], int):
        position = (stamp.position[0],
                    size_y - stamp.position[1] - stamp_size_y)
    else:
        position = (int(stamp.position[0] * size_x),
                    int(stamp.position[1] * size_y) - stamp_size_y)
    if stamp.scale_x != 1:
        stamp_im = stamp_im.resize((int(stamp_size_x * stamp.scale_x),
                                    int(stamp_size_y * stamp.scale_x)))
    tim.paste(stamp_im, position, mask=stamp_im)
    im = tim
    return im


def apply_stamp_text(im, stamp):
    size_x, size_y = im.size
    tim = im.convert("RGBA")
    txt_im = Image.new("RGBA", tim.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_im)
    color = stamp.color
    font = ImageFont.truetype(stamp.font, stamp.font_size)
    text = stamp.text
    w, h = draw.textsize(text, font=font)
    position = (int(stamp.position[0] * size_x - w / 2),
                int(stamp.position[1] * size_y))
    draw.text(position, text, fill=color, font=font)
    tim = Image.alpha_composite(tim, txt_im)
    im = tim
    return im


def try_convert_to_rgb(im):
    size_x, size_y = im.size
    pixels = im.load()

    if im.getbands() == ("R", "G", "B"):
        return im

    print("Checking for transparency")
    for y in range(size_y):
        for x in range(size_x):
            r, g, b, a = pixels[x, y]
            if a != 255:
                print("Image wasn't fully opaque, staying RGBA")
                return im
    return im.convert("RGB")


def convert_targets(base_path, settings, inputs, stamps):
    wanted_target = None
    wanted_conversion = None
    if len(sys.argv) >= 3:
        wanted_target = sys.argv[2]
    if len(sys.argv) >= 4:
        wanted_conversion = sys.argv[3]

    for target in settings["targets"]:
        if not "name" in target:
            continue

        target_name = target["name"]
        if wanted_target and target_name != wanted_target:
            print("Skipping", target_name)
            continue

        print()
        print("************************************")
        print("Target: ", target_name)
        out_dir_base = os.path.join(base_path, "targets", target_name)

        if not os.path.exists(out_dir_base):
            os.mkdir(out_dir_base)

        for conv in target["conversions"]:
            name = conv["name"]
            if wanted_conversion and wanted_conversion != name:
                print("Skipping", target_name, "/", name)
                continue

            out_filename_base = os.path.join(out_dir_base, name)

            print("")
            print("name:        ", name)
            if "input" in conv:
                input = inputs[conv["input"]]
                area = input.areas[conv["focus"]]
                input_filename = input.file
                im = Image.open(input_filename)
                im = apply_focus(im, area, conv)
            else:
                input_filename = os.path.join(base_path, conv["input_file"])
                im = Image.open(input_filename)

            # Stamp
            if "stamps" in conv:
                for stamp_name in conv["stamps"]:
                    stamp = stamps[stamp_name]
                    if hasattr(stamp, 'image'):
                        print("Applying stamp image")
                        im = apply_stamp_image(im, stamp)

                    if hasattr(stamp, 'text'):
                        print("Applying stamp text")
                        im = apply_stamp_text(im, stamp)

            # Vignette
            do_vignette = False
            if "apply_vignette" in conv:
                do_vignette = conv["apply_vignette"]
            if do_vignette:
                print("Applying vignette")
                im = apply_vignette(im)

            # Convert to RGB if possible
            im = try_convert_to_rgb(im)

            # Save
            print("Saving")
            out_filename = out_filename_base + ".png"
            im.save(out_filename)

            # Debug
        #     break
        # break


def main():
    script_file_path = os.path.realpath(__file__)
    script_dir = os.path.dirname(script_file_path)
    os.chdir(script_dir)

    settings_filename = sys.argv[1]

    with open(settings_filename, "r") as settings_file:
        settings = json.load(settings_file)

    base_path = os.path.dirname(settings_filename)
    print("Loading inputs...")
    inputs = load_inputs(base_path, settings)

    print("Loading stamps...")
    stamps = load_stamps(base_path, settings)

    print("Converting...")
    convert_targets(base_path, settings, inputs, stamps)


if __name__ == "__main__":
    # try:
    main()
# except Exception as e:
# print("Failboat:" + str(e))
