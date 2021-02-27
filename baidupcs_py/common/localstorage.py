from typing import Optional, List, Dict, Any

import os
from collections import OrderedDict

import sqlite3


RAPID_UPLOAD_TABLE = "rapid_upload"

CREATE_RAPID_UPLOAD_TABLE = f"""
CREATE TABLE IF NOT EXISTS {RAPID_UPLOAD_TABLE}
(
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    filename TEXT NULL,

    localpath TEXT NULL,
    remotepath TEXT NULL,

    encrypt_password TEXT NULL,
    encrypt_type TEXT NULL,

    user_id INTEGER NULL,
    user_name TEXT NULL,

    slice_md5 TEXT NOT NULL,
    content_md5 TEXT NOT NULL,
    content_crc32 TEXT NOT NULL,
    content_length INTEGER NOT NULL,

    record_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(slice_md5, content_md5, content_length, filename)
)
"""

RAPID_UPLOAD_TABLE_COLS = [
    c.strip().split(" ", 1)[0]
    for c in CREATE_RAPID_UPLOAD_TABLE.split("\n")
    if c.startswith("    ")
]

INSERT_RAPID_UPLOAD = f"""
INSERT OR IGNORE INTO {RAPID_UPLOAD_TABLE}
    (
        filename,

        localpath,
        remotepath,

        encrypt_password,
        encrypt_type,

        user_id,
        user_name,

        slice_md5,
        content_md5,
        content_crc32,
        content_length
    )
VALUES (?,?,?,?,?,?,?,?,?,?,?)
"""


class RapidUploadInfo:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)

        c = self._conn.cursor()
        c.execute(CREATE_RAPID_UPLOAD_TABLE)
        self._conn.commit()

    def insert(
        self,
        slice_md5: str,
        content_md5: str,
        content_crc32: int,  # not needed
        content_length: int,
        filename: Optional[str] = None,
        localpath: Optional[str] = None,
        remotepath: Optional[str] = None,
        encrypt_password: Optional[bytes] = None,
        encrypt_type: Optional[str] = None,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
    ):
        """Insert a rapid upload info"""

        c = self._conn.cursor()
        c.execute(
            INSERT_RAPID_UPLOAD,
            (
                filename,
                localpath,
                remotepath,
                encrypt_password,
                encrypt_type,
                user_id,
                user_name,
                slice_md5,
                content_md5,
                content_crc32,
                content_length,
            ),
        )
        self._conn.commit()

    def list(
        self,
        ids: List[int] = [],
        by_filename: bool = False,
        by_time: bool = False,
        by_size: bool = False,
        by_localpath: bool = False,
        by_remotepath: bool = False,
        by_user_id: bool = False,
        by_user_name: bool = False,
        desc: bool = False,
        limit: int = 0,
        offset: int = -1,
    ) -> List[Dict[str, Any]]:
        """List records by condition

        Default order by record_time and desc
        """

        if ids:
            ids_str = ",".join([str(i) for i in ids])
            sql = f"SELECT * FROM {RAPID_UPLOAD_TABLE} WHERE id IN ({ids_str})"
            c = self._conn.cursor()
            c.execute(sql)
            return [OrderedDict(zip(RAPID_UPLOAD_TABLE_COLS, r)) for r in c.fetchall()]

        if by_filename:
            condition = "order by filename"
        elif by_time:
            condition = "order by record_time"
        elif by_size:
            condition = "order by content_length"
        elif by_localpath:
            condition = "order by localpath"
        elif by_remotepath:
            condition = "order by remotepath"
        elif by_user_id:
            condition = "order by user_id"
        elif by_user_name:
            condition = "order by user_name"
        else:
            condition = "order by record_time"
            desc = True

        if desc:
            condition += " desc"

        if limit > 0:
            condition += f" LIMIT {limit}"

        if offset > 0:
            condition += f" OFFSET {offset}"

        sql = f"SELECT * FROM {RAPID_UPLOAD_TABLE} {condition}"

        c = self._conn.cursor()
        c.execute(sql)
        return [OrderedDict(zip(RAPID_UPLOAD_TABLE_COLS, r)) for r in c.fetchall()]

    def search(
        self,
        keyword: str,
        in_filename: bool = False,
        in_localpath: bool = False,
        in_remotepath: bool = False,
        in_user_name: bool = False,
        in_md5: bool = False,
    ) -> List[Dict[str, Any]]:

        keyword = keyword.replace("'", r"\'")

        conditions = []
        if in_filename:
            conditions.append(f"filename LIKE '%{keyword}%'")
        if in_localpath:
            conditions.append(f"localpath LIKE '%{keyword}%'")
        if in_remotepath:
            conditions.append(f"remotepath LIKE '%{keyword}%'")
        if in_user_name:
            conditions.append(f"user_name LIKE '%{keyword}%'")
        if in_md5:
            conditions.append(f"content_md5 LIKE '%{keyword}%'")

        if not conditions:
            conditions = [
                f"filename LIKE '%{keyword}%'",
                f"localpath LIKE '%{keyword}%'",
                f"remotepath LIKE '%{keyword}%'",
                f"user_name LIKE '%{keyword}%'",
                f"content_md5 LIKE '%{keyword}%'",
            ]

        condition = "WHERE " + " OR ".join(conditions)

        if keyword:
            sql = f"SELECT * FROM {RAPID_UPLOAD_TABLE} {condition}"
        else:
            sql = f"SELECT * FROM {RAPID_UPLOAD_TABLE}"

        c = self._conn.cursor()
        c.execute(sql)
        return [OrderedDict(zip(RAPID_UPLOAD_TABLE_COLS, r)) for r in c.fetchall()]

    def delete(self, id: int):
        sql = f"DELETE FROM {RAPID_UPLOAD_TABLE} WHERE id = ?"

        c = self._conn.cursor()
        c.execute(sql, (id,))
        self._conn.commit()


def save_rapid_upload_info(
    rapiduploadinfo_file: str,
    slice_md5: str,
    content_md5: str,
    content_crc32: int,  # not needed
    content_length: int,
    localpath: Optional[str] = None,
    remotepath: Optional[str] = None,
    encrypt_password: bytes = b"",
    encrypt_type: str = "",
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
):
    rapiduploadinfo = RapidUploadInfo(rapiduploadinfo_file)
    rapiduploadinfo.insert(
        slice_md5.lower(),
        content_md5.lower(),
        content_crc32,
        content_length,
        filename=os.path.basename(remotepath or ""),
        localpath=localpath,
        remotepath=remotepath,
        encrypt_password=encrypt_password,
        encrypt_type=encrypt_type,
        user_id=user_id,
        user_name=user_name,
    )
