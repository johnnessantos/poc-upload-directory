import logging
from io import BytesIO

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from google.cloud.storage import Client
from PIL import Image

app = FastAPI()

logging.basicConfig(
    format='%(levelname)s %(asctime)s %(name)s.%(filename)s:%(lineno)d == %(message)s',
    level='DEBUG'
)
logger = logging.getLogger(__name__)


class ImageThumbnail:

    @staticmethod
    def _thumbnail(file: BytesIO, extension: str, width: int, height: int) -> BytesIO:
        image = Image.open(file)
        image.thumbnail((width, height))
        img_io = BytesIO()
        image.save(img_io, extension.upper())
        img_io.seek(0)
        return img_io


class ImageProcessor(ImageThumbnail):

    def __init__(self, file: BytesIO, file_name: str) -> None:
        self.file = file
        self.file_name = file_name

    def get_extension(self) -> str:
        index = self.file_name.find('.')
        if index > 0:
            return self.file_name[index+1:]
        return None

    def thumbnail(self, width: int, height: int) -> BytesIO:
        return self._thumbnail(self.file, self.get_extension(), width, height)


@app.get(
    '/images/thumbnail/{width}x{height}/{filename}',
    response_description='Returns a thumbnail image from a larger image',
    response_class=StreamingResponse,
    responses={200: {'description': 'an image'},
               404: {'descripton': 'not found'}}
)
def thumbnail_image(width: int, height: int, filename: str) -> StreamingResponse:
    filename = '0000000000001b.png'

    file = open(f'./{filename}', 'rb')
    file_bytes = BytesIO(file.read())
    file.close()

    image_processor = ImageProcessor(file_bytes, filename)
    imgio = image_processor.thumbnail(width, height)

    logger.info(
        f'Processed filename:{filename} returned size:{imgio.__sizeof__()}'
    )

    return StreamingResponse(
        content=imgio,
        media_type=f'image/{image_processor.get_extension()}'
    )


@app.get(
    '/images/bucket/thumbnail/{width}x{height}/{file_path:path}',
    response_description='Google Cloud Storage',
    response_class=StreamingResponse,
    responses={200: {'description': 'an image'},
               404: {'descripton': 'not found'}}
)
def thumbnail_image(width: int, height: int, file_path: str) -> StreamingResponse:
    bucket_name = 'upload-directory'
    storage_client = Client()
    bucket = storage_client.bucket(bucket_name)

    file_blob = bucket.blob(file_path)
    file_bytes = BytesIO(file_blob.download_as_bytes(timeout=60))

    image_processor = ImageProcessor(file_bytes, file_path)
    imgio = image_processor.thumbnail(width, height)

    logger.info(
        f'Processed filename:{file_path} returned size:{imgio.__sizeof__()}'
    )

    return StreamingResponse(
        content=imgio,
        media_type=f'image/{image_processor.get_extension()}'
    )
