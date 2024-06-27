#!/usr/bin/env python3

import os

import requests
import qbittorrentapi
from typing import List, Union
from time import sleep
from urllib.parse import urljoin
from datetime import datetime, timedelta


class MTFreeAutoTask:
    def __init__(
            self,
            qb_url: str,
            qb_user: str,
            qb_password: str,
            qb_port: int,
            mt_base_url: str,
            mt_api_key: str,
            pause: bool = True,
    ) -> None:
        self.tag = "mt_free_auto_task"
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
        self.pause = pause

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
            free_end_time = datetime.strptime(
                row["status"].get("discountEndTime"), "%Y-%m-%d %H:%M:%S"
            ).timestamp()
            free_list.append({
                "id": row["id"],
                "small_descr": row.get("smallDescr", ""),
                "free_end_time": free_end_time,
                "size": int(row["size"]),
                "seeders": int(row["status"].get("seeders")),
                "leechers": int(row["status"].get("seeders"))
            })
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
        print("add torrent: %s" % str(link))
        if tags is None:
            tags = []
        elif isinstance(tags, str):
            tags = [tags]
        tags.append(self.tag)
        self.qb_client.torrents_add(
            urls=[link],
            is_paused=self.pause,
            tags=tags,
        )

    def qb_remove_torrent(self, hashs: Union[str, List[str]]):
        if isinstance(hashs, str):
            hashs = [hashs]
        print("remove torrent")
        self.qb_client.torrents_delete(
            delete_files=True,
            hashs=hashs,
        )

    def qb_remove_torrent_by_tag(self, tag: str):
        torrents = self.qb_client.torrents_info(
            tag=tag
        )
        for torrent in torrents:
            self.qb_remove_torrent(torrent.hash)

    def run(self):
        print("MTFreeAutoTask run begin")
        free_end_limit = (datetime.now() + timedelta(days=5)).timestamp()
        torrent_remove_limit = (datetime.now() + timedelta(days=1)).timestamp()
        for mode in ["adult", "normal"]:
            for free_info in self.mt_search_free(mode):
                id_tag = "mt_%s" % free_info["id"]
                if free_info["free_end_time"] < torrent_remove_limit:
                    self.qb_remove_torrent_by_tag(id_tag)
                    continue
                elif free_info["free_end_time"] < free_end_limit:
                    continue
                else:
                    torrent_link = self.mt_get_torrent_link(free_info["id"])
                    self.qb_add_torrent(torrent_link, [id_tag])
        print("MTFreeAutoTask run end")


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
        qb_url, qb_user, qb_password, int(qb_port), mt_base_url, mt_api_key
    ).run()


run_task()
