import json
import os
from datetime import datetime
import aiofiles
from aiofiles import os as aio_os

from app.utils.config_handler import chroma_conf
from app.utils.path_tool import get_abs_path
from app.utils.logger_handler import logger


class MD5Store:
    """
    MD5存储管理器
    MD5 存储类，用于存储文档的 MD5 值。
    """

    def __init__(self):
        self.base_dir = os.path.dirname(get_abs_path(chroma_conf['md5_hex_store']))

    def _get_md5_store_dir(self, user_id: str = None) -> str:
        """
        获取MD5存储目录
        :param user_id: 用户ID，为None时返回公共目录
        :return: MD5存储目录路径
        """
        if user_id:
            return os.path.join(self.base_dir, 'user_md5', user_id) # 用户目录
        else:
            return os.path.join(self.base_dir, 'public_md5') # 公共目录

    async def check_md5_hex(self, md5_for_check: str, user_id: str = None) -> bool:
        """
        异步检查md5
        :param md5_for_check: 要检查的MD5值
        :param user_id: 用户ID，为None时检查公共知识库
        :return: 是否存在
        """
        md5_dir = self._get_md5_store_dir(user_id) # 获取MD5存储目录
        md5_path = os.path.join(md5_dir, 'md5.txt') # 获取MD5存储文件路径

        if not await aio_os.path.exists(md5_dir):
            # 如果存储文件不存在，则创建一个空的存储文件
            await aio_os.makedirs(md5_dir, exist_ok=True)
            async with aiofiles.open(md5_path, 'w', encoding='utf-8'):
                pass
            return False

        if not await aio_os.path.exists(md5_path):
            # 如果存储文件不存在，则创建一个空的存储文件
            async with aiofiles.open(md5_path, 'w', encoding='utf-8'):
                pass
            return False

        try:
            async with aiofiles.open(md5_path, 'r', encoding='utf-8') as f:
                async for line in f:
                    line = line.strip() # 去除行首尾空格
                    if not line:
                        continue   # 跳过空行
                    if line.startswith('{'): # 尝试解析JSON
                        try:
                            data = json.loads(line) # 尝试解析JSON
                            if data.get('md5') == md5_for_check:
                                return True # 如果MD5匹配，则返回True
                        except json.JSONDecodeError:  # 解析失败
                            if line == md5_for_check:
                                return True
                    else: # 尝试直接匹配MD5
                        if line == md5_for_check:
                            return True
            return  False # 没有匹配的MD5，返回False
        except Exception as e:
            logger.error(f"【向量数据库】检查MD5时出错: {e}")
            return False

    async def save_md5_hex(self, md5_hex: str, filename: str = None, original_filename: str = None, user_id: str = None):
        """
        异步保存md5
        :param md5_hex: 要保存的MD5值
        :param filename: 文件名（可选）
        :param original_filename: 原始文件名（可选）
        :param user_id: 用户ID，为None时保存到公共知识库
        """
        md5_dir = self._get_md5_store_dir(user_id)
        md5_path = os.path.join(md5_dir, 'md5.txt')

        if not await aio_os.path.exists(md5_dir):
            await aio_os.makedirs(md5_dir, exist_ok=True)

        data = {
            'md5': md5_hex,
            'filename': filename,
            'original_filename': original_filename,
            'upload_time': datetime.now().isoformat() # 上传时间
        }

        async with aiofiles.open(md5_path, 'a', encoding='utf-8') as f:
            await f.write(json.dumps(data, ensure_ascii=False) + '\n') # 写入JSON

    def save_md5_hex_sync(self, md5_hex: str, filename: str = None, original_filename: str = None, user_id: str = None):
        """
        同步保存md5 （用于多线程场景）
        :param md5_hex: 要保存的MD5值
        :param filename: 文件名（可选）
        :param original_filename: 原始文件名（可选）
        :param user_id: 用户ID，为None时保存到公共知识库
        """
        md5_dir = self._get_md5_store_dir(user_id)
        md5_path = os.path.join(md5_dir, 'md5.txt')

        if not os.path.exists(md5_dir):
            os.makedirs(md5_dir, exist_ok=True)

        data = {
            'md5': md5_hex,
            'filename': filename,
            'original_filename': original_filename,
            'upload_time': datetime.now().isoformat() # 上传时间
        }

        with open(md5_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(data, ensure_ascii=False) + '\n')

    async def _read_md5_records(self, user_id: str = None) -> tuple:
        """
        读取用户的MD5记录文件
        :param user_id: 用户ID，为None时读取公共知识库
        :return: (file_path, records列表)，每条记录为dict
        """
        md5_dir = self._get_md5_store_dir(user_id)
        md5_path = os.path.join(md5_dir, 'md5.txt')

        if not await aio_os.path.exists(md5_path):
            return md5_path, [] # 如果文件不存在，则返回空列表

        records = [] # 存储记录
        async with aiofiles.open(md5_path, 'r', encoding='utf-8') as f:
            async for line in f:
                line = line.strip() # 去除行首尾空格
                if not line:
                    continue   # 跳过空行
                if line.startswith('{'): # 尝试解析JSON
                    try:
                        records.append(json.loads(line)) # 尝试解析JSON, 添加到列表中
                    except json.JSONDecodeError:  # 解析失败: # 解析失败
                        records.append({
                            'md5': line,
                            'filename': None,
                            'original_filename': None,
                            'upload_time':  None
                        })
                else: # 尝试直接匹配MD5
                    records.append({
                        'md5': line,
                        'filename': None,
                        'original_filename': None,
                        'upload_time':  None
                    }) # 添加到列表中, 没有原始文件名
        return md5_path, records # 返回文件路径和记录列表, 每条记录为dict, 包含md5, filename, original_filename, upload_time字段

    async def _write_md5_records(self, md5_path: str, records: list):
        """
        写入MD5记录文件，空列表时自动清理文件及目录
        :param md5_path: 文件路径
        :param records: 记录列表
        """
        if not records: # 如果记录列表为空，则删除文件及目录
            md5_dir = os.path.dirname(md5_path)
            if await aio_os.path.exists(md5_path): # 如果文件存在，则删除文件
                await aio_os.remove(md5_path)
            if await aio_os.path.exists(md5_dir): # 如果目录存在，则删除目录
                try:
                    await aio_os.rmdir(md5_dir)
                except OSError:
                    pass
            return

        async with aiofiles.open(md5_path, 'w', encoding='utf-8') as f:
            for record in records:
                await f.write(json.dumps(record, ensure_ascii=False) + '\n')

    async def delete_user_md5(self, user_id: str):
        """
        删除用户的整个MD5记录目录
        :param user_id: 用户ID
        """
        md5_dir = self._get_md5_store_dir(user_id)
        md5_path = os.path.join(md5_dir, 'md5.txt')
        if await aio_os.path.exists(md5_path): # 如果文件存在，则删除文件
            await aio_os.remove(md5_path)
        if await aio_os.path.exists(md5_dir): # 如果目录存在，则删除目录
            await aio_os.rmdir(md5_dir)
        logger.info(f"【MD5存储】已删除用户 {user_id} 的MD5记录")


    async def delete_by_filename(self, user_id: str, filename: str):
        """
        通过文件名删除MD5记录
        :param user_id: 用户ID
        :param filename: 文件名
        :return: 被删记录的md5值，不存在返回None
        """
        md5_path, records = await self._read_md5_records(user_id) # 读取MD5记录，返回文件路径和记录列表，
        if not records: # 如果记录列表为空，则返回None
            return None

        found_md5 = None # 存储被删除的md5值, 初始化为None
        remaining = [] # 存储剩余的记录, 用于写入新的记录文件
        for record in records:
            record_filename = record.get('filename', record.get('original_filename')) # 获取文件名, 如果没有，则使用原始文件名, 如果原始文件名也没有，则使用md5值, 如果md5值也没有，则返回None
            if record_filename == filename: # 如果文件名匹配
                found_md5 = record.get('md5') # 获取md5值
            else: # 如果文件名不匹配
                remaining.append(record) # 添加到剩余的记录列表中

        if found_md5 is None:
            return None

        await self._write_md5_records(md5_path, remaining) # 写入新的记录文件, 剩余的记录列表
        logger.info(f"【MD5存储】已删除用户 {user_id} 的文件 {filename} 的MD5记录")
        return found_md5 # 返回被删除的md5值

    async def delete_single_md5(self, user_id: str, md5_to_delete: str) -> bool:
        """
        删除单个MD5记录
        :param user_id: 用户ID
        :param md5_to_delete: 要删除的MD5值
        :return: 是否成功删除
        """
        md5_path, records = await self._read_md5_records(user_id)
        if not records:
            return False

        remaining = [r for r in records if r.get('md5') != md5_to_delete] # 剩余的记录列表, 用于写入新的记录文件, 排除要删除的记录
        if len(remaining) == len(records): # 如果没有剩余的记录, 则返回失败
            return False

        await self._write_md5_records(md5_path, remaining)
        logger.info(f"【MD5存储】已删除用户 {user_id} 的MD5记录: {md5_to_delete}")
        return True

    async def get_md5_info(self, user_id: str, md5_value: str):
        """
        获取MD5对应的文档信息
        :param user_id: 用户ID
        :param md5_value: MD5值
        :return: MD5信息字典，不存在返回None
        """
        _, records = await self._read_md5_records(user_id) # 读取MD5记录，返回文件路径和记录列表,，
        # 遍历记录列表，返回第一个匹配的记录，
        # 如果没有匹配的记录，则返回None，否则返回匹配的记录，匹配的记录包含md5, filename, original_filename, upload_time字段，匹配的记录为dict
        for record in records:
            if record.get('md5') == md5_value:
                return record
        return None

    async def get_all_md5_info(self, user_id: str):
        """
        获取所有MD5对应的文档信息
        :param user_id: 用户ID
        :return: MD5信息列表，不存在返回None
        """
        _, records = await self._read_md5_records(user_id) # 读取MD5记录，返回文件路径和记录列表,，
        return records