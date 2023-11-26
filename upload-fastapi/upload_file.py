import asyncio
import logging
from json import dumps
from typing import Annotated, Optional
from uuid import uuid4

from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, field_validator

logging.basicConfig(
    format='%(levelname)s %(asctime)s %(name)s.%(filename)s:%(lineno)d == %(message)s',
    level='DEBUG'
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix='/uploads')

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=False,
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
        if file_path.endswith(extension):
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


DATABASE = {
    'upload': {},
    'media': {}
}


def upload_insert_one(id: str, data: dict) -> bool:
    DATABASE['upload'].update({'fake': data})
    return True


def upload_find_one(id: str) -> Optional[dict]:
    return DATABASE['upload'].get(id)


class UploadFileReponseDTO(BaseModel):
    file_path: str
    completed: bool = False
    errors: list[str] = []


class UploadResponseDTO(BaseModel):
    upload_id: str
    files: list[UploadFileReponseDTO]
    status: str = 'in_progress'

    def is_valid_upload(self) -> bool:
        for upload_file in self.files:
            if not upload_file.errors:
                return True
        return False

    def cancel_upload(self) -> None:
        self.status = 'canceled'


@router.post(path='', tags=['Uploads'], status_code=status.HTTP_201_CREATED)
async def start_upload(upload: UploadRequestDTO) -> UploadResponseDTO:
    upload_response = UploadResponseDTO(
        upload_id=generate_upload_id(),
        files=[
            UploadFileReponseDTO(
                file_path=file,
                errors=[] if check_valid_file(upload.content_type, file) else [
                    'invalid_file']
            )
            for file in upload.file_paths
        ]
    )

    if upload_response.is_valid_upload():
        upload_insert_one(upload_response.upload_id,
                          upload_response.model_dump())
        logger.info(f'Starting upload:{upload_response.model_dump()}')
    else:
        upload_response.cancel_upload()
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
    upload_response = upload_find_one(upload_id)
    if not upload_response:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                'message': 'Not found upload',
                'data': {}
            },
        )

    return upload_response


async def generate_events(request: Request):
    while request.is_disconnected:
        data = dumps(upload_find_one('fake') or {})
        yield f'data:{data}\n\n'
        await asyncio.sleep(1)
    logger.debug(f'Finishing stream events')


@app.get('/{upload_id}/sse/')
def sse(request: Request, upload_id: str):
    logger.info(f'Starting monitoring upload_id:{upload_id}')
    return StreamingResponse(
        generate_events(request),
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
        await websocket.send_json(upload_find_one(upload_id))


@router.post(path='/files', tags=['Uploads'])
async def create_files(files: Annotated[list[bytes], File()]):
    raise_files(files)
    return {'file_sizes': [len(file) for file in files]}


@router.post(path='/upload', tags=['Uploads'])
async def create_upload_files(files: list[UploadFile]):
    upload_report = upload_find_one('fake')
    logger.info(upload_report)
    for file in files:
        for file_uploaded in upload_report['files']:
            if file_uploaded['file_path'] == file.filename:
                file_path = file_uploaded['file_path']
                file_uploaded['completed'] = True
                logger.info(
                    f'update {file.filename} file_path:{file_path} result:{file_uploaded}')
        upload_insert_one('fake', upload_report)
        await asyncio.sleep(3)

    await asyncio.sleep(3)
    upload_report['status'] = 'completed'
    upload_insert_one('fake', upload_report)
    return {'filenames': [file.filename for file in files]}

app.include_router(router)
