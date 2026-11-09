"""
Percha · servicio de segmentación de prendas.

Instalar:  pip install fastapi "uvicorn[standard]" python-multipart "rembg[cpu]" pillow numpy
Ejecutar:  uvicorn main:app --host 0.0.0.0 --port 8000
Opcional: CLASSIFY=1 (pip install transformers torch) · MATTING=0 para ir más rápido
Modelo:    REMBG_MODEL=u2net (defecto) | isnet-general-use | u2net_cloth_seg
"""
import io
import os

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from PIL import Image, ImageOps
from rembg import new_session, remove

MAX_BYTES = 8 * 1024 * 1024
MAX_SIDE = 1024

app = FastAPI(title="Percha Garment API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),  # en producción: tu dominio
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
    expose_headers=["X-Dominant-Color", "X-Category", "X-Pattern", "X-Fabric"],
)

session = new_session(os.getenv("REMBG_MODEL", "u2net"))  # se carga una vez al iniciar


def dominant_color(img: Image.Image) -> str:
    """Color dominante: cuantización (median cut) de los píxeles opacos; elige el grupo más grande."""
    arr = np.asarray(img.convert("RGBA"))
    px = arr[arr[..., 3] > 200][:, :3]
    if len(px) == 0:
        return "#808080"
    if len(px) > 20000:
        px = px[np.random.default_rng(0).choice(len(px), 20000, replace=False)]
    q = Image.fromarray(px.reshape(-1, 1, 3).astype("uint8")).quantize(colors=6, method=Image.Quantize.MEDIANCUT)
    pal = np.array(q.getpalette()[:18]).reshape(-1, 3)
    counts = np.bincount(np.asarray(q).ravel(), minlength=len(pal))[: len(pal)]
    r, g, b = pal[counts.argmax()]
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


# --- Clasificación opcional (CLIP zero-shot). Activar con CLASSIFY=1 e instalar transformers + torch ---
GROUPS = {
    "category": {"Vestidos": "a dress", "Poleras": "a t-shirt, shirt or sweater", "Chaquetas": "a jacket or coat",
                 "Pantalones": "pants, jeans or a skirt", "Calzado": "shoes, sneakers or boots",
                 "Accesorios": "a handbag, hat or accessory"},
    "pattern": {"liso": "a plain solid color garment", "rayas": "a striped garment", "cuadros": "a plaid checkered garment",
                "floral": "a floral print garment", "puntos": "a polka dot garment"},
    "fabric": {"mezclilla": "a denim garment", "algodon": "a cotton garment", "lana": "a knitted wool garment",
               "cuero": "a leather garment", "seda": "a silky satin garment"},
}
_clip = None


def classify(cut: Image.Image) -> dict:
    global _clip
    if os.getenv("CLASSIFY", "0") != "1":
        return {}
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        if _clip is None:
            name = "openai/clip-vit-base-patch32"
            _clip = (CLIPModel.from_pretrained(name).eval(), CLIPProcessor.from_pretrained(name))
        model, proc = _clip
        bg = Image.new("RGB", cut.size, "white")
        bg.paste(cut, mask=cut.getchannel("A"))
        out = {}
        for key, labels in GROUPS.items():
            inp = proc(text=list(labels.values()), images=bg, return_tensors="pt", padding=True)
            with torch.no_grad():
                p = model(**inp).logits_per_image.softmax(-1)[0]
            out[key] = list(labels.keys())[int(p.argmax())]
        return out
    except Exception as e:  # sin modelo/torch: la app sigue funcionando sin etiquetas
        print("classify:", e)
        return {}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/remove-background")
def remove_bg(file: UploadFile = File(...)):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(415, "Sube una imagen (JPG, PNG o WebP).")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "La imagen pesa más de 8 MB.")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception:
        raise HTTPException(400, "No se pudo leer la imagen.")

    img.thumbnail((MAX_SIDE, MAX_SIDE))
    cut = remove(img, session=session,  # PNG RGBA con fondo transparente
                 alpha_matting=os.getenv("MATTING", "1") == "1",  # bordes finos (pelusa, tul)
                 alpha_matting_foreground_threshold=240, alpha_matting_background_threshold=10,
                 alpha_matting_erode_size=8)

    bbox = cut.getchannel("A").getbbox()  # recorta márgenes vacíos
    if bbox is None:
        raise HTTPException(422, "No se detectó ninguna prenda. Prueba con mejor luz y fondo liso.")
    cut = cut.crop(bbox)

    buf = io.BytesIO()
    cut.save(buf, format="PNG", optimize=True)
    headers = {"X-Dominant-Color": dominant_color(cut)}
    for k, v in classify(cut).items():
        headers["X-" + k.capitalize()] = v
    return Response(buf.getvalue(), media_type="image/png", headers=headers)
