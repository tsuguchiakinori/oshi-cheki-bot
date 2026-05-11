import os
import time
import random
import hashlib
from datetime import datetime, timedelta

from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    ImageMessage,
    TextSendMessage,
    ImageSendMessage,
    QuickReply,
    QuickReplyButton,
    MessageAction,
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
user_filters = {}

MAX_TEXT_LENGTH = 14


def user_key(user_id):
    return hashlib.md5(user_id.encode()).hexdigest()


def load_font(size):
    try:
        return ImageFont.truetype("makiirclehand.ttf", size)
    except Exception:
        return ImageFont.load_default()


def split_text(text):
    if len(text) <= 10:
        return [text]
    mid = len(text) // 2
    return [text[:mid], text[mid:]]


def fit_text(draw, text, max_width, start_size=78, min_size=36):
    size = start_size
    while size >= min_size:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return font
        size -= 2
    return load_font(min_size)


def get_text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def add_light_vignette(img, alpha=28):
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = img.size

    d.rectangle((0, 0, w, 55), fill=(40, 30, 20, alpha))
    d.rectangle((0, h - 55, w, h), fill=(40, 30, 20, alpha))
    d.rectangle((0, 0, 55, h), fill=(40, 30, 20, alpha))
    d.rectangle((w - 55, 0, w, h), fill=(40, 30, 20, alpha))

    overlay = overlay.filter(ImageFilter.GaussianBlur(42))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def apply_photo_filter(img, filter_type, variant=0):
    # variant=0 / 1 で違いが分かるように強めに差分を作る

    if filter_type == "emo":
        if variant == 0:
            # エモい：あたたかめ
            img = ImageEnhance.Color(img).enhance(0.68)
            img = ImageEnhance.Contrast(img).enhance(1.10)
            img = ImageEnhance.Brightness(img).enhance(0.96)

            warm = Image.new("RGB", img.size, (255, 224, 188))
            img = Image.blend(img, warm, 0.22)

            sepia = Image.new("RGB", img.size, (125, 85, 52))
            img = Image.blend(img, sepia, 0.04)

            noise = Image.effect_noise(img.size, 12).convert("RGB")
            img = Image.blend(img, noise, 0.035)

            img = add_light_vignette(img, alpha=30)
            img = img.filter(ImageFilter.GaussianBlur(0.08))

        else:
            # エモい：暗めフィルム
            img = ImageEnhance.Color(img).enhance(0.58)
            img = ImageEnhance.Contrast(img).enhance(1.16)
            img = ImageEnhance.Brightness(img).enhance(0.88)

            warm = Image.new("RGB", img.size, (245, 214, 178))
            img = Image.blend(img, warm, 0.26)

            sepia = Image.new("RGB", img.size, (105, 70, 45))
            img = Image.blend(img, sepia, 0.07)

            noise = Image.effect_noise(img.size, 16).convert("RGB")
            img = Image.blend(img, noise, 0.052)

            img = add_light_vignette(img, alpha=44)
            img = img.filter(ImageFilter.GaussianBlur(0.12))

    elif filter_type == "bright":
        if variant == 0:
            # 盛れる：明るめ
            img = ImageEnhance.Color(img).enhance(1.08)
            img = ImageEnhance.Contrast(img).enhance(1.14)
            img = ImageEnhance.Brightness(img).enhance(1.16)

            cool = Image.new("RGB", img.size, (236, 244, 255))
            img = Image.blend(img, cool, 0.05)

            noise = Image.effect_noise(img.size, 5).convert("RGB")
            img = Image.blend(img, noise, 0.01)

            img = add_light_vignette(img, alpha=12)

        else:
            # 盛れる：白っぽめ
            img = ImageEnhance.Color(img).enhance(0.95)
            img = ImageEnhance.Contrast(img).enhance(1.07)
            img = ImageEnhance.Brightness(img).enhance(1.24)

            white = Image.new("RGB", img.size, (255, 250, 240))
            img = Image.blend(img, white, 0.13)

            cool = Image.new("RGB", img.size, (238, 246, 255))
            img = Image.blend(img, cool, 0.08)

            noise = Image.effect_noise(img.size, 4).convert("RGB")
            img = Image.blend(img, noise, 0.008)

            img = add_light_vignette(img, alpha=8)

    else:
        if variant == 0:
            # いい感じ：自然
            img = ImageEnhance.Color(img).enhance(0.82)
            img = ImageEnhance.Contrast(img).enhance(1.07)
            img = ImageEnhance.Brightness(img).enhance(1.03)

            warm = Image.new("RGB", img.size, (255, 234, 202))
            img = Image.blend(img, warm, 0.11)

            sepia = Image.new("RGB", img.size, (120, 82, 50))
            img = Image.blend(img, sepia, 0.018)

            noise = Image.effect_noise(img.size, 7).convert("RGB")
            img = Image.blend(img, noise, 0.022)

            img = add_light_vignette(img, alpha=20)
            img = img.filter(ImageFilter.GaussianBlur(0.05))

        else:
            # いい感じ：淡め
            img = ImageEnhance.Color(img).enhance(0.72)
            img = ImageEnhance.Contrast(img).enhance(0.96)
            img = ImageEnhance.Brightness(img).enhance(1.09)

            cream = Image.new("RGB", img.size, (255, 242, 218))
            img = Image.blend(img, cream, 0.17)

            noise = Image.effect_noise(img.size, 8).convert("RGB")
            img = Image.blend(img, noise, 0.025)

            img = add_light_vignette(img, alpha=16)
            img = img.filter(ImageFilter.GaussianBlur(0.07))

    return img


def draw_soft_stain(base, x, y, rx, ry, color, alpha, blur=18):
    stain = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(stain)
    d.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(color[0], color[1], color[2], alpha))
    stain = stain.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(base.convert("RGBA"), stain).convert("RGB")


def add_edge_and_bottom_stains(base, width, height):
    edge_count = random.randint(2, 4)

    for _ in range(edge_count):
        side = random.choice(["left", "right", "top", "bottom"])

        if side == "left":
            x = random.randint(-40, 45)
            y = random.randint(0, height)
        elif side == "right":
            x = random.randint(width - 45, width + 40)
            y = random.randint(0, height)
        elif side == "top":
            x = random.randint(0, width)
            y = random.randint(-35, 45)
        else:
            x = random.randint(0, width)
            y = random.randint(height - 220, height + 30)

        rx = random.randint(18, 55)
        ry = random.randint(10, 38)
        color = random.choice([
            (190, 178, 150),
            (205, 192, 165),
            (176, 160, 132),
            (220, 207, 181),
        ])
        alpha = random.randint(8, 16)

        base = draw_soft_stain(base, x, y, rx, ry, color, alpha, blur=random.randint(12, 22))

    bottom_count = random.randint(1, 3)

    for _ in range(bottom_count):
        x = random.randint(80, width - 80)
        y = random.randint(1010, height - 60)
        rx = random.randint(25, 75)
        ry = random.randint(10, 35)

        color = random.choice([
            (196, 184, 155),
            (212, 198, 170),
            (180, 164, 138),
        ])
        alpha = random.randint(6, 14)

        base = draw_soft_stain(base, x, y, rx, ry, color, alpha, blur=random.randint(16, 26))

    return base


def make_old_paper_frame(width, height):
    base = Image.new("RGB", (width, height), "#f3eddf")

    warm = Image.new("RGB", (width, height), (255, 239, 210))
    base = Image.blend(base, warm, 0.23)

    noise = Image.effect_noise((width, height), 12).convert("RGB")
    base = Image.blend(base, noise, 0.025)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)

    d.rectangle((0, 0, width, 55), fill=(185, 170, 145, 20))
    d.rectangle((0, height - 90, width, height), fill=(190, 175, 150, 22))
    d.rectangle((0, 0, 55, height), fill=(185, 170, 145, 18))
    d.rectangle((width - 55, 0, width, height), fill=(185, 170, 145, 18))

    overlay = overlay.filter(ImageFilter.GaussianBlur(45))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")

    base = add_edge_and_bottom_stains(base, width, height)

    return base


def round_corners(img, radius=18):
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.size[0], img.size[1]), radius, fill=255)
    img.putalpha(mask)
    return img


def draw_hand_text(base_img, text, x, y, font):
    draw = ImageDraw.Draw(base_img)
    current_x = x

    for char in text:
        bbox = draw.textbbox((0, 0), char, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        char_img = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((20, 20), char, font=font, fill=(30, 30, 30))

        char_img = char_img.rotate(random.uniform(-2, 2), resample=Image.BICUBIC, expand=True)

        base_img.paste(
            char_img,
            (int(current_x + random.randint(-1, 1)), int(y + random.randint(-2, 2))),
            char_img
        )

        current_x += w + random.randint(3, 6)


def draw_centered_multiline_text(frame, text, draw):
    lines = split_text(text)

    max_width = 820
    longest_line = max(lines, key=len)
    font = fit_text(draw, longest_line, max_width=max_width, start_size=78, min_size=36)

    if len(lines) == 1:
        start_y = 1035
        line_gap = 0
    else:
        start_y = 1000
        line_gap = 72

    for i, line in enumerate(lines):
        line_width = get_text_width(draw, line, font)
        x = (1000 - line_width) // 2
        y = start_y + i * line_gap
        draw_hand_text(frame, line, x, y, font)


def make_cheki(user_id, variant=0):
    key = user_key(user_id)
    filter_type = user_filters.get(user_id, "good")

    img = Image.open(f"/tmp/input_{key}.jpg").convert("RGB")

    w, h = img.size
    size = min(w, h)
    img = img.crop(((w - size) // 2, (h - size) // 2, (w + size) // 2, (h + size) // 2))
    img = img.resize((900, 900))
    img = apply_photo_filter(img, filter_type, variant=variant)
    img = round_corners(img, radius=18)

    frame = make_old_paper_frame(1000, 1300)

    photo_x = 50 + random.randint(-6, 6)
    photo_y = 80 + random.randint(-5, 5)
    frame.paste(img, (photo_x, photo_y), img)

    draw = ImageDraw.Draw(frame)

    text = user_texts.get(user_id, "")
    date = user_dates.get(user_id, "")

    lines = split_text(text)
    draw_centered_multiline_text(frame, text, draw)

    date_font = load_font(40)
    if date:
        date_width = get_text_width(draw, date, date_font)
        date_x = (1000 - date_width) // 2

        if len(lines) == 1:
            date_y = 1133
        else:
            date_y = 1205

        draw.text((date_x, date_y), date, fill=(125, 125, 118), font=date_font)

    final_noise = Image.effect_noise(frame.size, 5 + variant).convert("RGB")
    frame = Image.blend(frame, final_noise, 0.008 + variant * 0.001)

    output_key = f"{key}_{variant}"
    frame.save(f"/tmp/output_{output_key}.jpg", quality=92)
    return output_key


def date_quick_reply():
    today = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y.%m.%d")
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="今日", text=today)),
        QuickReplyButton(action=MessageAction(label="なし", text="なし")),
    ])


def filter_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="いい感じ", text="いい感じ")),
        QuickReplyButton(action=MessageAction(label="エモい", text="エモい")),
        QuickReplyButton(action=MessageAction(label="盛れる", text="盛れる")),
    ])


def after_generate_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="もう一回つくる", text="やり直し")),
        QuickReplyButton(action=MessageAction(label="雰囲気だけ変える", text="雰囲気だけ変える")),
        QuickReplyButton(action=MessageAction(label="文字だけ変える", text="文字変更")),
        QuickReplyButton(action=MessageAction(label="日付だけ変える", text="日付変更")),
    ])


@app.route("/")
def home():
    return "OK"


@app.route("/output/<key>.jpg")
def output(key):
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


def generate_and_send(user_id):
    output_keys = []
    for i in range(2):
        output_keys.append(make_cheki(user_id, variant=i))

    line_bot_api.push_message(
        user_id,
        TextSendMessage(text="2パターン作ったよ📸\n好きな方を保存してね👇")
    )

    for output_key in output_keys:
        image_url = f"{BASE_URL}/output/{output_key}.jpg?{int(time.time())}"
        line_bot_api.push_message(
            user_id,
            ImageSendMessage(
                original_content_url=image_url,
                preview_image_url=image_url
            )
        )

    line_bot_api.push_message(
        user_id,
        TextSendMessage(
            text="いい感じにできたね📸✨\nSNSでシェアしてみて👇\n#オシフィルム\n\nもう一回つくる？",
            quick_reply=after_generate_quick_reply()
        )
    )


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    user_id = event.source.user_id
    key = user_key(user_id)

    content = line_bot_api.get_message_content(event.message.id)

    with open(f"/tmp/input_{key}.jpg", "wb") as f:
        for chunk in content.iter_content():
            f.write(chunk)

    user_states[user_id] = "filter"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(
            text="どの雰囲気にする？👇",
            quick_reply=filter_quick_reply()
        )
    )


@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    if msg == "やり直し":
        user_states[user_id] = None
        user_filters[user_id] = "good"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="もう一度画像を送ってね📸")
        )
        return

    if msg == "雰囲気だけ変える":
        user_states[user_id] = "filter_change"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="どの雰囲気に変える？👇", quick_reply=filter_quick_reply())
        )
        return

    if msg == "文字変更":
        user_states[user_id] = "text"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="新しい文字を送って！")
        )
        return

    if msg == "日付変更":
        user_states[user_id] = "date"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="日付を送ってね📅 手入力でもOK。不要なら「なし」", quick_reply=date_quick_reply())
        )
        return

    if user_states.get(user_id) in ["filter", "filter_change"]:
        filter_map = {
            "いい感じ": "good",
            "エモい": "emo",
            "盛れる": "bright"
        }

        if msg in filter_map:
            user_filters[user_id] = filter_map[msg]

            if user_states.get(user_id) == "filter_change":
                user_states[user_id] = None
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"「{msg}」で作り直すね📸")
                )
                generate_and_send(user_id)
                return

            user_states[user_id] = "text"

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"「{msg}」で作るね📸\n下に入れる文字を送って！")
            )
            return

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="ボタンから雰囲気を選んでね👇", quick_reply=filter_quick_reply())
        )
        return

    if user_states.get(user_id) == "text":
        if len(msg) > MAX_TEXT_LENGTH:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"文字は{MAX_TEXT_LENGTH}文字までにして🙏")
            )
            return

        user_texts[user_id] = msg
        user_states[user_id] = "date"

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="日付を送ってね📅 手入力でもOK。不要なら「なし」", quick_reply=date_quick_reply())
        )
        return

    if user_states.get(user_id) == "date":
        user_dates[user_id] = "" if msg in ["なし", "無し", "不要", "いらない"] else msg

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="2パターン現像中…📸")
        )

        generate_and_send(user_id)

        user_states[user_id] = None
        return

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="まず画像を送ってね📸")
    )
