"""
文件处理工具类
"""


import os, hashlib, aiofiles, asyncio, sys

from app.utils.logger_handler import logger

from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredPDFLoader, \
    UnstructuredMarkdownLoader, UnstructuredPowerPointLoader
from app.utils.path_tool import get_abs_path


class FontBBoxStreamFilter:
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        if "FontBBox from font descriptor" not in data:
            self.stream.write(data)

    def flush(self):
        self.stream.flush()     # 刷新缓冲区

sys.stderr = FontBBoxStreamFilter(sys.stderr)  # 屏蔽字体警告信息

"""
这段代码创建了一个过滤器类 `FontBBoxStreamFilter`，
用于拦截标准错误输出（stderr）。它重写了 `write()` 方法，
过滤掉包含 "FontBBox from font descriptor" 的日志信息，
其他内容正常写入。最后通过替换 `sys.stderr` 实现全局过滤，屏蔽特定的字体警告信息。
"""


async def get_file_md5_hex(file_path: str) -> str:  # 获取文件的md5的十六进制字符串
    """获取文件的md5值"""
    # 处理路径，确保使用绝对路径
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path

    if not os.path.exists(abs_file_path):
        logger.error(f"[md5计算]文件{abs_file_path}不存在")
        return  ""

    if not os.path.isfile(abs_file_path):
        logger.error(f"[md5计算]路径{abs_file_path}不是文件")
        return  ""

    md5_obj = hashlib.md5()   # 创建md5对象

    chunk_size = 4096  # 4KB分片，避免文件过大爆内存
    try:
        async with aiofiles.open(abs_file_path, "rb") as f:  # 必须二进制读取
            while chunk := await f.read(chunk_size):
                md5_obj.update(chunk)

            """
            chunk = f.read(chunk_size)
            while chunk:

                md5_obj.update(chunk)
                chunk = f.read(chunk_size)
            """
            md5_hex = md5_obj.hexdigest()
            return md5_hex
    except Exception as e:
        logger.error(f"计算文件{abs_file_path}md5失败，{str(e)}")
        return ""


async def listdir_allowed_type(path: str, allowed_types: tuple[str]) -> tuple:  # 返回文件夹内的文件列表（允许的文件后缀）
    """
     获取指定目录下所有允许的文件类型
     :param path: 目录路径
     :param allowed_types: 允许的文件类型元组
     :return: 符合条件的文件路径列表
     """
    # 处理路径，确保使用绝对路径
    abs_path = get_abs_path(path) if not os.path.isabs(path) else path
    files = []

    if not os.path.exists(abs_path):
        logger.error(f"【文件列表】目录路径 {abs_path}不存在")
        return allowed_types

    if not os.path.isdir(abs_path):
        logger.error(f"【文件列表】目录路径 {abs_path}不是文件夹")
        return tuple(allowed_types)

    for f in await asyncio.to_thread(os.listdir, abs_path):
        if f.endswith(allowed_types):
            files.append(os.path.join(abs_path, f))

    return tuple(files)


async def pdf_loader(file_path: str, password: str = None) -> list[Document]:
    """
    加载PDF文件内容（支持包含图片和文字的混合PDF）
    :param file_path: PDF文件路径
    :param password: PDF密码（如果有）
    :return: PDF文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path  # 处理路径，确保使用绝对路径

    if password:
        loader = PyPDFLoader(abs_file_path, password=password)
        return await asyncio.to_thread(loader.load)

    try:
        loader = UnstructuredPDFLoader(abs_file_path)  # 创建加载器
        docs = await asyncio.to_thread(loader.load)  # 加载文件
        if docs and any(len(doc.page_content.strip() > 0 for doc in docs)): # 判断是否有内容
            return docs
    except Exception as e:
        logger.warning(f"【PDF加载】UnstructuredPDFLoader失败，尝试PyPDFLoader: {e}")

    loader = PyPDFLoader(abs_file_path)
    return await asyncio.to_thread(loader.load)  # 加载文件


async def txt_loader(file_path: str) -> list[Document]:
    """
    加载TXT文件内容
    :param file_path: TXT文件路径
    :return: TXT文件内容
    """
    # 处理路径，确保使用绝对路径
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path

    # 使用不同的编码加载文件
    encodings = ['utf-8', 'gbk']
    for encoding in encodings:
        try:
            loader = TextLoader(abs_file_path, encoding=encoding)
            return await asyncio.to_thread(loader.load)
        except Exception as e:
            logger.error(f"【文本文件加载】使用编码 {encoding} 加载文件 {abs_file_path} 时出错: {e}")
            continue
        # 所有编码都失败，返回空列表
    return []


async def word_loader(file_path: str) -> list[Document]:
    """
    加载WORD文件内容
    :param file_path: WORD文件路径
    :return: WORD文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path
    try:
        loader = TextLoader(abs_file_path, encoding='utf-8')
        return await asyncio.to_thread(loader.load)
    except Exception as e:
        logger.error(f"【WORD文件加载】加载文件 {abs_file_path} 时出错: {e}")
        return []

async def markdown_loader(file_path: str) -> list[Document]:
    """
    加载Markdown文件内容
    :param file_path: Markdown文件路径
    :return: Markdown文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path
    try:
        loader = UnstructuredMarkdownLoader(abs_file_path, mode="single")  # mode="single", 为单文件模式
        return await asyncio.to_thread(loader.load)
    except Exception as e:
        logger.error(f"【Markdown文件加载】加载文件 {abs_file_path} 时出错: {e}")
        return []

async def ppt_loader(file_path: str) -> list[Document]:
    """
    加载PPT/PPTX文件内容
    :param file_path: PPT文件路径
    :return: PPT文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path
    try:
        loader = UnstructuredPowerPointLoader(abs_file_path, mode="single")
        return await asyncio.to_thread(loader.load)
    except Exception as e:
        logger.error(f"【PPT文件加载】加载文件 {abs_file_path} 时出错: {e}")
        return []


def get_file_md5_hex_sync(file_path: str) -> str:
    """同步获取文件的md5值（用于多线程场景）"""
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path

    if not os.path.exists(abs_file_path):
        logger.error(f"【md5计算】文件路径 {abs_file_path} 不存在")
        return ""

    if not os.path.isfile(abs_file_path):
        logger.error(f"【md5计算】文件路径 {abs_file_path} 不是文件")
        return ""

    md5_object = hashlib.md5()
    chunk_size = 1024
    try:
        with open(abs_file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                md5_object.update(chunk)
    except Exception as e:
        logger.error(f"【md5计算】读取文件 {abs_file_path} 时出错: {e}")
        return ""

    return md5_object.hexdigest()


def pdf_loader_sync(file_path: str, password: str = None) -> list[Document]:
    """
    同步加载PDF文件内容（用于多线程场景，支持包含图片和文字的混合PDF）
    :param file_path: PDF文件路径
    :param password: PDF密码（如果有）
    :return: PDF文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path

    if password:
        loader = PyPDFLoader(abs_file_path, password=password)
        return loader.load()

    try:
        loader = UnstructuredPDFLoader(abs_file_path)
        docs = loader.load()
        if docs and any(len(doc.page_content.strip()) > 0 for doc in docs):
            return docs
    except Exception as e:
        logger.warning(f"【PDF加载】UnstructuredPDFLoader失败，尝试PyPDFLoader: {e}")

    loader = PyPDFLoader(abs_file_path)
    return loader.load()


def txt_loader_sync(file_path: str) -> list[Document]:
    """
    同步加载TXT文件内容（用于多线程场景）
    :param file_path: TXT文件路径
    :return: TXT文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path

    encodings = ['utf-8', 'gbk']
    for encoding in encodings:
        try:
            loader = TextLoader(abs_file_path, encoding=encoding)
            return loader.load()
        except Exception as e:
            logger.error(f"【文本文件加载】使用编码 {encoding} 加载文件 {abs_file_path} 时出错: {e}")
            continue
    return []


def word_loader_sync(file_path: str) -> list[Document]:
    """
    同步加载WORD文件内容（用于多线程场景）
    :param file_path: WORD文件路径
    :return: WORD文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path
    try:
        loader = TextLoader(abs_file_path, encoding='utf-8')
        return loader.load()
    except Exception as e:
        logger.error(f"【WORD文件加载】加载文件 {abs_file_path} 时出错: {e}")
        return []


def markdown_loader_sync(file_path: str) -> list[Document]:
    """
    同步加载Markdown文件内容（用于多线程场景）
    :param file_path: Markdown文件路径
    :return: Markdown文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path
    try:
        loader = UnstructuredMarkdownLoader(abs_file_path, mode="single")
        return loader.load()
    except Exception as e:
        logger.error(f"【Markdown文件加载】加载文件 {abs_file_path} 时出错: {e}")
        return []


def ppt_loader_sync(file_path: str) -> list[Document]:
    """
    同步加载PPT/PPTX文件内容（用于多线程场景）
    :param file_path: PPT文件路径
    :return: PPT文件内容
    """
    abs_file_path = get_abs_path(file_path) if not os.path.isabs(file_path) else file_path
    try:
        loader = UnstructuredPowerPointLoader(abs_file_path, mode="single")
        return loader.load()
    except Exception as e:
        logger.error(f"【PPT文件加载】加载文件 {abs_file_path} 时出错: {e}")
        return []

# 测试代码
if __name__ == '__main__':
    print(get_file_md5_hex_sync("app/utils/file_handler.py"))

