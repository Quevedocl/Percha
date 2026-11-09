"""
Percha · servicio de segmentación de prendas.

Instalar:  pip install fastapi "uvicorn[standard]" python-multipart "rembg[cpu]" pillow numpy
Ejecutar:  uvicorn main:app --host 0.0.0.0 --port 8000
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
    expose_headers=["X-Dominant-Color"],
)

session = new_session(os.getenv("REMBG_MODEL", "u2net"))  # se carga una vez al iniciar


def dominant_color(img: Image.Image) -> str:
    """Color medio de los píxeles opacos de la prenda, en hex."""
    arr = np.asarray(img.convert("RGBA"))
    px = arr[arr[..., 3] > 200][:, :3]
    if len(px) == 0:
        return "#808080"
    r, g, b = np.median(px, axis=0).astype(int)
    return f"#{r:02x}{g:02x}{b:02x}"


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
    cut = remove(img, session=session)  # PNG RGBA con fondo transparente

    bbox = cut.getchannel("A").getbbox()  # recorta márgenes vacíos
    if bbox is None:
        raise HTTPException(422, "No se detectó ninguna prenda. Prueba con mejor luz y fondo liso.")
    cut = cut.crop(bbox)

    buf = io.BytesIO()
    cut.save(buf, format="PNG", optimize=True)
    return Response(buf.getvalue(), media_type="image/png",
                    headers={"X-Dominant-Color": dominant_color(cut)})
