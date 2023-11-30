import asyncio
import logging
from json import dumps
from os import getenv
from time import perf_counter
from typing import Annotated, Optional
from uuid import uuid4

import motor.motor_asyncio
from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

logging.basicConfig(
    format='%(levelname)s %(asctime)s %(name)s.%(filename)s:%(lineno)d == %(message)s',
    level='DEBUG'
)
logger = logging.getLogger(__name__)


client = motor.motor_asyncio.AsyncIOMotorClient(
    getenv('MONGO_URL', 'mongodb://localhost:27017')
)
database = client['upload']
collection = database['upload']


async def upload_insert_one(id: str, data: dict) -> bool:
    await collection.update_one({'upload_id': id}, {'$set': data}, upsert=True)
    return True


async def upload_find_one(id: str) -> Optional[dict]:
    return await collection.find_one({'upload_id': id}, {'_id': 0})


async def upload_update_upload_file(upload_id: str, file_path: str):
    logger.info(f'Uploading upload_id:{upload_id} file_path:{file_path}')
    await collection.update_one(
        {'upload_id': upload_id, 'files.file_path': file_path},
        {'$set': {'files.$.completed': True}}
    )


async def upload_send_to_bucket(file):
    await asyncio.sleep(0.5)


async def process_file(upload_id: str, file: UploadFile):
    await upload_send_to_bucket(file)
    await upload_update_upload_file(upload_id, file.filename)


async def process(upload_id: str, files: list[UploadFile]):
    start_time: float = perf_counter()
    upload_report = await upload_find_one(upload_id)
    logger.info(upload_report)

    tasks = [process_file(upload_id, file) for file in files]
    asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    await upload_insert_one(upload_id, {'status': 'completed'})
    start_time = perf_counter() - start_time
    logger.info(f'Processed upload_id:{upload_id} in {start_time:.4f}s')

router = APIRouter(prefix='/uploads')

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def generate_upload_id() -> str:
    return str(uuid4())


def raise_files(files):
    logging.info([
        {
            'file_name': file.filename,
            'size': file.size,
            'headers': file.headers.items()
        }
        for file in files
    ])


VALIDS_CONTENT_TYPES = ['images', 'audios', 'podcasts', 'special_content']
VALIDS_EXTENSIONS_PER_TYPE = {
    'images': ['jpg', 'jpeg', 'png'],
    'audios': ['mp3'],
    'podcasts': ['mp3'],
    'special_content': ['*']
}


def check_valid_file(content_type: str, file_path: str) -> bool:
    for extension in VALIDS_EXTENSIONS_PER_TYPE[content_type]:
        if '*' in extension or file_path.endswith(extension):
            return True
    logger.warning(f'Invalid file:{file_path} for content_type:{content_type}')
    return False


class UploadRequestDTO(BaseModel):
    content_type: str
    file_paths: list[str]

    @field_validator('content_type')
    @classmethod
    def check_valid_content_type(cls, v: str) -> str:
        if v in VALIDS_CONTENT_TYPES:
            return v

        logger.error(f'Invalid content_type:{v}')
        raise ValueError(f'Invalid content_type:{v}')

    model_config = {
        'json_schema_extra': {
            'examples': [{'content_type': 'images', 'file_paths': ['ean/image.jpg']}]
        }
    }


class UploadFileReponseDTO(BaseModel):
    file_path: str
    completed: bool = False
    errors: list[str] = []

    def check_error(self, content_type: str):
        self.errors = (
            []
            if check_valid_file(content_type, self.file_path)
            else ['invalid_file']
        )


class UploadResponseDTO(BaseModel):
    upload_id: str
    content_type: str
    files: list[UploadFileReponseDTO]
    status: str = 'in_progress'

    def is_valid_upload(self) -> bool:
        for upload_file in self.files:
            if not upload_file.errors:
                return True
        return False

    def valid_extensions(self):
        for file in self.files:
            file.check_error(self.content_type)

    def cancel_upload(self) -> None:
        self.status = 'canceled'


@router.post(path='', tags=['Uploads'], status_code=status.HTTP_201_CREATED)
async def start_upload(upload: UploadRequestDTO) -> UploadResponseDTO:
    upload_response = UploadResponseDTO(
        upload_id=generate_upload_id(),
        content_type=upload.content_type,
        files=[
            UploadFileReponseDTO(file_path=file)
            for file in upload.file_paths
        ]
    )

    upload_response.valid_extensions()

    if upload_response.is_valid_upload():
        await upload_insert_one(
            upload_response.upload_id,
            upload_response.model_dump()
        )
        logger.info(f'Starting upload:{upload_response.model_dump()}')
    else:
        upload_response.cancel_upload()
        await upload_insert_one(
            upload_response.upload_id,
            upload_response.model_dump()
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'message': 'No valid file',
                'data': upload_response.model_dump()
            },
        )

    return upload_response


@router.post(path='/report', tags=['Uploads'])
async def upload_report(upload_id: str) -> UploadResponseDTO:
    upload_response = await upload_find_one(upload_id)
    if not upload_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'message': 'Not found upload',
                'data': {}
            },
        )

    return upload_response


async def generate_events(upload_id: str, request: Request):
    while request.is_disconnected:
        data = dumps(await upload_find_one(upload_id) or {})
        yield f'data:{data}\n\n'
        await asyncio.sleep(1)
    logger.debug(f'Finishing stream events')


@app.get('/{upload_id}/sse/')
def sse(request: Request, upload_id: str):
    logger.info(f'Starting monitoring upload_id:{upload_id}')
    return StreamingResponse(
        generate_events(upload_id, request),
        media_type='text/event-stream'
    )


@app.get('/')
def index():
    return {'status': 'ok'}


@router.websocket('/{upload_id}/ws')
async def ws_upload(websocket: WebSocket, upload_id: str):
    await websocket.accept()
    while True:
        # data = await websocket.receive_text()
        await websocket.send_json(await upload_find_one(upload_id))


@router.post(path='/files', tags=['Uploads'])
async def create_files(files: Annotated[list[bytes], File()]):
    raise_files(files)
    return {'file_sizes': [len(file) for file in files]}


@router.post(path='/{upload_id}/upload', tags=['Uploads'])
async def create_upload_files(upload_id: str, files: list[UploadFile]):
    logger.info(f'Starting processing files upload_id:{upload_id}')
    await process(upload_id, files)
    return {'filenames': [file.filename for file in files]}

app.include_router(router)
