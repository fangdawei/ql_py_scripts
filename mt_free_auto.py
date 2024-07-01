#!/usr/bin/env python3

import os

import requests
import asyncio
import qbittorrentapi
import telegram
from typing import List, Union
from time import sleep
from urllib.parse import urljoin
from datetime import datetime, timedelta

BYTES_GB = 1024 * 1024 * 1024


class MTFreeAutoTask:
    def __init__(
        self,
        qb_url: str,
        qb_user: str,
        qb_password: str,
        qb_port: int,
        mt_base_url: str,
        mt_api_key: str,
        add_free_days: int,
        remove_free_hours: int,
        file_size_limit_gb: int,
        clear_days: int,
    ) -> None:
        print("add_free_days: %d" % add_free_days)
        print("remove_free_hours: %d" % remove_free_hours)
        print("file_size_limit_gb: %d" % file_size_limit_gb)
        print("clear_days: %d" % clear_days)
        self.tag = "mt_free_auto"
        self.mt_base_url = mt_base_url
        self.mt_api_key = mt_api_key
        self.headers = {
            "x-api-key": mt_api_key,
        }
        self.qb_client = qbittorrentapi.Client(
            host=qb_url,
            port=qb_port,
            username=qb_user,
            password=qb_password,
        )
        self.add_free_days = add_free_days
        self.remove_free_hours = remove_free_hours
        self.file_size_limit = file_size_limit_gb * BYTES_GB
        self.clear_days = clear_days

    @staticmethod
    def return_safe_response(response):
        if response.ok:
            return response
        else:
            response.raise_for_status()

    def mt_request(self, path, *args, **kwargs):
        sleep(5)
        response = requests.post(
            urljoin(self.mt_base_url, path),
            headers=self.headers,
            *args,
            **kwargs,
        )
        return self.return_safe_response(response)

    def mt_search_free(self, mode):
        print("mt free in [%s] searching..." % mode)
        response = self.mt_request(
            "api/torrent/search",
            json={
                "mode": mode,
                "categories": [],
                "visible": 1,
                "pageNumber": 1,
                "pageSize": 50,
            },
        )
        free_list = []
        for row in response.json()["data"]["data"]:
            if not row["status"]["discount"] == "FREE":
                continue
            if row["status"].get("discountEndTime"):
                free_end_time = datetime.strptime(
                    row["status"].get("discountEndTime"), "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            else:
                free_end_time = (datetime.now() + timedelta(days=365)).timestamp()
            free_list.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "small_descr": row.get("smallDescr", ""),
                    "free_end_time": free_end_time,
                    "size": int(row["size"]),
                    "seeders": int(row["status"].get("seeders", 0)),
                    "leechers": int(row["status"].get("leechers", 0)),
                }
            )
        return free_list

    def mt_get_torrent_link(self, torrent_id):
        response = self.mt_request(
            "api/torrent/genDlToken",
            files={
                "id": (None, torrent_id),
            },
        )
        if response.json()["message"] == "SUCCESS":
            return response.json()["data"]
        return None

    def qb_add_torrent(self, link: str, tags: Union[str, List[str]] = None):
        print("add torrent to qb: %s" % str(link))
        if tags is None:
            tags = []
        elif isinstance(tags, str):
            tags = [tags]
        tags.append(self.tag)
        self.qb_client.torrents_add(
            urls=[link],
            is_paused=False,
            tags=tags,
        )

    def qb_remove_torrents(self, hashs: Union[str, List[str]]):
        if isinstance(hashs, str):
            hashs = [hashs]
        print("remove torrent from qb: %s" % str(hashs))
        self.qb_client.torrents_delete(
            delete_files=True,
            hashs=hashs,
        )

    def qb_remove_torrents_by_tag(self, tag: str):
        torrents = self.qb_client.torrents_info(tag=tag)
        for torrent in torrents:
            self.qb_remove_torrents(torrent.hash)

    def qb_clear_torrents(self):
        torrents = self.qb_client.torrents_info(tag=self.tag)
        torrent_clear_limit = (
            datetime.now() - timedelta(days=self.clear_days)
        ).timestamp()
        remove_hashs = []
        for torrent in torrents:
            if torrent.added_on < torrent_clear_limit:
                remove_hashs.append(torrent.hash)
        if len(remove_hashs) > 0:
            self.qb_remove_torrents(remove_hashs)

    def qb_has_torrent_with_tag(self, tag: str) -> bool:
        torrents = self.qb_client.torrents_info(tag=tag)
        return len(torrents) > 0

    def qb_delete_tags(self, tags: Union[str, List[str]]):
        if isinstance(tags, str):
            tags = [tags]
        self.qb_client.torrents_delete_tags(tags)

    @staticmethod
    def free_info_print_str(free_info: dict) -> str:
        result = {}
        for k, v in free_info.items():
            if k == "free_end_time":
                result[k] = datetime.fromtimestamp(v).strftime("%Y-%m-%d %H:%M:%S")
            elif k == "size":
                result[k] = "%d GB" % int(v / BYTES_GB)
            else:
                result[k] = v
        return str(result)

    @staticmethod
    def free_info_msg_str(free_info: dict) -> str:
        free_end_time = datetime.fromtimestamp(free_info["free_end_time"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        return (
            f"[种子名称]: {free_info['name']}\n"
            + f"[种子描述]: {free_info['small_descr']}\n"
            + f"[文件大小]: {int(free_info['size']/BYTES_GB)} GB\n"
            + f"[做种数]: {free_info['seeders']}\n"
            + f"[下载数]: {free_info['leechers']}\n"
            + f"[FREE到期时间]: {free_end_time}"
        )

    def run(self):
        print("auto task run begin")
        self.qb_clear_torrents()
        free_add_deadline = (
            datetime.now() + timedelta(days=self.add_free_days)
        ).timestamp()
        free_remove_deadline = (
            datetime.now() + timedelta(hours=self.remove_free_hours)
        ).timestamp()
        for mode in ["adult", "normal"]:
            free_list = self.mt_search_free(mode)
            print("[%s] free torrent count: %d" % (mode, len(free_list)))
            for free_info in free_list:
                id_tag = "mt_%s" % free_info["id"]
                if free_info["free_end_time"] < free_remove_deadline:
                    if self.qb_has_torrent_with_tag(id):
                        print(
                            "auto remove free torrent: %s"
                            % self.free_info_print_str(free_info)
                        )
                        self.qb_remove_torrents_by_tag(id_tag)
                        self.qb_delete_tags(id_tag)
                        send_telegram_msg(
                            "MT FREE 种子删除通知", self.free_info_msg_str(free_info)
                        )
                    continue
                elif free_info["free_end_time"] < free_add_deadline:
                    continue
                elif free_info["size"] < self.file_size_limit:
                    continue
                elif self.qb_has_torrent_with_tag(id_tag):
                    continue
                else:
                    print(
                        "auto add free torrent: %s"
                        % self.free_info_print_str(free_info)
                    )
                    torrent_link = self.mt_get_torrent_link(free_info["id"])
                    self.qb_add_torrent(torrent_link, [id_tag])
                    send_telegram_msg(
                        "MT FREE 种子下载通知", self.free_info_msg_str(free_info)
                    )
        print("auto task run end")


def send_telegram_msg(title: str, content: str):
    """
    使用 telegram 机器人 推送消息。
    """
    if not os.environ.get("MT_AUTO_TG_BOT_TOKEN"):
        print("MT_AUTO_TG_BOT_TOKEN not set! skip TG msg!")
        return
    tg_bot_token = os.environ.get("MT_AUTO_TG_BOT_TOKEN")
    if not os.environ.get("MT_AUTO_TG_CHAT_ID"):
        print("MT_AUTO_TG_CHAT_ID not set! skip TG msg!")
        return
    tg_chat_id = os.environ.get("MT_AUTO_TG_CHAT_ID")
    print("TG msg sending...")
    bot = telegram.Bot(token=tg_bot_token)
    try:
        asyncio.run(
            bot.send_message(
                chat_id=str(tg_chat_id),
                text=f"{title}\n\n{content}",
                disable_web_page_preview=True,
            )
        )
        print("TG msg send success!")
    except Exception as e:
        print("TG msg send fail! %s" % str(e))


def run_task():
    qb_url = os.environ["QB_URL"]
    if not qb_url:
        raise Exception("Miss QB_URL")
    qb_user = os.environ["QB_USER"]
    if not qb_user:
        raise Exception("Miss QB_USER")
    qb_password = os.environ["QB_PASSWORD"]
    if not qb_password:
        raise Exception("Miss QB_PASSWORD")
    qb_port = os.environ["QB_PORT"]
    if not qb_port:
        raise Exception("Miss QB_PORT")
    mt_base_url = os.environ["MT_BASE_URL"]
    if not mt_base_url:
        raise Exception("Miss MT_BASE_URL")
    mt_api_key = os.environ["MT_API_KEY"]
    if not mt_api_key:
        raise Exception("Miss MT_API_KEY")
    MTFreeAutoTask(
        qb_url,
        qb_user,
        qb_password,
        int(qb_port),
        mt_base_url,
        mt_api_key,
        int(os.environ.get("MT_AUTO_ADD_FREE_DAYS", "5")),
        int(os.environ.get("MT_AUTO_REMOVE_FREE_HOURS", "12")),
        int(os.environ.get("MT_AUTO_FILE_SIZE_LIMIT_GB", "15")),
        int(os.environ.get("MT_AUTO_CLEAR_DAYS", "7")),
    ).run()


run_task()
