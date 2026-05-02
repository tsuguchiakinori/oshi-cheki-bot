import os
import time
import random
import hashlib
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    ImageMessage,
    TextSendMessage,
    ImageSendMessage,
)
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ["CHANNEL_ACCESS_TOKEN"]
CHANNEL_SECRET = os.environ["CHANNEL_SECRET"]
BASE_URL = "https://oshi-cheki-bot.onrender.com"

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

user_states = {}
user_texts = {}
user_dates = {}


def user_key(user_id):
    return hashlib.md5(user_id.encode()).hexdigest()


def load_font(size):
    try:
        return ImageFont.truetype("makiirclehand.ttf", size)
    except:
        return ImageFont.load_default()


def fit_text(draw, text, max_width, start_size=74, min_size=36):
    size = start_size
    while size >= min_size:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            return font
        size -= 4
    return load_font(min_size)


def apply_cheki_filter(img):
    img = ImageEnhance.Color(img).enhance(0.86)
    img = ImageEnhance.Contrast(img).enhance(1.04)
    img = ImageEnhance.Brightness(img).enhance(1.06)

    warm = Image.new("RGB", img.size, (255, 242, 218))
    img = Image.blend(img, warm, 0.12)

    noise = Image.effect_noise(img.size, 8).convert("RGB")
    img = Image.blend(img, noise, 0.045)

    img = img.filter(ImageFilter.GaussianBlur(0.18))
    return img


def apply_frame_texture(frame):
    w, h = frame.size

    warm = Image.new("RGB", (w, h), (255, 248, 235))
    frame = Image.blend(frame, warm, 0.16)

    noise = Image.effect_noise((w, h), 12).convert("RGB")
    frame = Image.blend(frame, noise, 0.045)

    # 下に向かって少しだけ紙が沈む感じ
    gradient = Image.new("L", (1, h))
    for y in range(h):
        value = int(255 * (y / h) * 0.22)
        gradient.putpixel((0, y), value)

    alpha = gradient.resize((w, h))
    bottom_shadow = Image.new("RGB", (w, h), (225, 222, 215))
    frame = Image.composite(bottom_shadow, frame, alpha)

    return frame


def draw_hand_text(base_img, text, x, y, font, fill=(35, 35, 35), spacing=3):
    draw = ImageDraw.Draw(base_img)
    current_x = x

    for char in text:
        char_bbox = draw.textbbox((0, 0), char, font=font)
        char_w = char_bbox[2] - char_bbox[0]
        char_h = char_bbox[3] - char_bbox[1]

        char_img = Image.new("RGBA", (char_w + 40, char_h + 40), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)

        char_draw.text((20, 20), char, font=font, fill=fill)

        angle = random.uniform(-2.2, 2.2)
        char_img = char_img.rotate(angle, resample=Image.BICUBIC, expand=True)

        offset_x = random.randint(-1, 2)
        offset_y = random.randint(-2, 2)

        base_img.paste(
            char_img,
            (int(current_x + offset_x), int(y + offset_y)),
            char_img
        )

        current_x += char_w + spacing + random.randint(0, 3)


def make_rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def make_cheki(user_id):
    key = user_key(user_id)
    input_path = f"/tmp/input_{key}.jpg"
    output_path = f"/tmp/output_{key}.jpg"

    text = user_texts.get(user_id, "My Oshi")
    date = user_dates.get(user_id, "")

    img = Image.open(input_path).convert("RGB")

    # 正方形トリミング
    w, h = img.size
    size = min(w, h)
    img = img.crop(((w - size) // 2, (h - size) // 2, (w + size) // 2, (h + size) // 2))

    img = img.resize((900, 900))
    img = apply_cheki_filter(img)

    # チェキ本体
    frame = Image.new("RGB", (1000, 1300), "#f8f6f1")
    frame = apply_frame_texture(frame)
    frame.paste(img, (50, 80))

    draw = ImageDraw.Draw(frame)

    text_font = fit_text(draw, text, max_width=840, start_size=76, min_size=40)
    date_font = load_font(42)

    # メインテキスト中央配置
    text_bbox = draw.textbbox((0, 0), text, font=text_font)
    text_w = text_bbox[2] - text_bbox[0]
    text_x = (1000 - text_w) // 2

    # ほんの少し影を入れて手書き感
    draw_hand_text(frame, text, text_x + 2, 1032, text_font, fill=(210, 205, 198), spacing=3)
    draw_hand_text(frame, text, text_x, 1030, text_font, fill=(35, 35, 35), spacing=3)

    if date:
        date_bbox = draw.textbbox((0, 0), date, font=date_font)
        date_w = date_bbox[2] - date_bbox[0]
        date_x = (1000 - date_w) // 2

        draw.text((date_x + 1, 1131), date, fill=(210, 205, 198), font=date_font)
        draw.text((date_x, 1130), date, fill=(115, 115, 112), font=date_font)

    # 角丸
    frame_rgba = frame.convert("RGBA")
    mask = make_rounded_mask(frame_rgba.size, 26)
    frame_rgba.putalpha(mask)

    # 少しだけ傾ける
    angle = random.uniform(-1.2, 1.2)
    rotated = frame_rgba.rotate(
        angle,
        resample=Image.BICUBIC,
        expand=True,
        fillcolor=(230, 227, 222, 0)
    )

    # 背景
    final_bg = Image.new("RGBA", (1120, 1440), (229, 227, 222, 255))

    # 影
    shadow = Image.new("RGBA", rotated.size, (0, 0, 0, 0))
    shadow_alpha = rotated.getchannel("A").filter(ImageFilter.GaussianBlur(10))
    shadow.putalpha(shadow_alpha)

    x = (1120 - rotated.size[0]) // 2
    y = (1440 - rotated.size[1]) // 2

    final_bg.alpha_composite(shadow, (x + 16, y + 18))
    final_bg.alpha_composite(rotated, (x, y))

    final = final_bg.convert("RGB")
    final.save(output_path, quality=95)

    return key


@app.route("/", methods=["GET"])
def home():
    return "OK"


@app.route("/output/<key>.jpg", methods=["GET"])
def output_image(key):
    return send_file(f"/tmp/output_{key}.jpg", mimetype="image/jpeg")


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    key = user_key(user_id)

    message_content = line_bot_api.get_message_content(event.message.id)

    with open(f"/tmp/input_{key}.jpg", "wb") as f:
        for chunk in message_content.iter_content():
            f.write(chunk)

    user_states[user_id] = "waiting_text"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="画像受け取ったで📸\n下に入れる文字を送って！")
    )


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()
    state = user_states.get(user_id)

    if state == "waiting_text":
        user_texts[user_id] = msg
        user_states[user_id] = "waiting_date"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"文字を設定したで📸\n「{msg}」\n次に日付を送って！不要なら「なし」")
        )
        return

    if state == "waiting_date":
        if msg in ["なし", "無し", "いらない", "不要"]:
            user_dates[user_id] = ""
        else:
            user_dates[user_id] = msg

        key = make_cheki(user_id)
        image_url = f"{BASE_URL}/output/{key}.jpg?v={int(time.time())}"

        user_states[user_id] = None

        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )
        )
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="まず画像を送ってね📸")
    )
