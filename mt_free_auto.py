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

    def get_payload(self, mode="adult", page_num=1, page_size=50, categories=[]):
        return {
            "mode": mode,
            "categories": categories,
            "visible": 1,
            "pageNumber": page_num,
            "pageSize": page_size,
        }

    @staticmethod
    def return_safe_response(response):
        if response.ok:
            return response
        else:
            response.raise_for_status()

    def requests(self, path, *args, **kwargs):
        sleep(5)
        response = requests.post(
            urljoin(self.mt_base_url, path),
            headers=self.headers,
            *args,
            **kwargs,
        )
        return self.return_safe_response(response)

    def search(self, mode, return_id=True):
        response = self.requests(
            "api/torrent/search",
            json=self.get_payload(mode),
        )
        if return_id:
            big_ids = []
            for row in response.json()["data"]["data"]:
                if not row["status"]["discount"] == "FREE":
                    continue
                free_end_time = datetime.strptime(
                    row["status"].get("discountEndTime"), "%Y-%m-%d %H:%M:%S"
                ).timestamp()
                free_end_before = (datetime.now() + timedelta(days=5)).timestamp()
                if free_end_time < free_end_before:
                    continue
                small_title = row.get("smallDescr", "")
                print(f"{small_title}: {self.mt_base_url}detail/{row['id']}")
                big_ids.append(row["id"])

            return big_ids
        else:
            return []

    def get_torrent(self, torrent_id, return_link=True):
        response = self.requests(
            "api/torrent/genDlToken",
            files={
                "id": (None, torrent_id),
            },
        )
        if return_link and response.json()["message"] == "SUCCESS":
            print(f"downloading : {torrent_id}")
            return response.json()["data"]

    def add_torrent(self, links: Union[str, List[str]]):
        if isinstance(links, str):
            links = [links]
        self.qb_client.torrents_add(
            urls=links,
            is_paused=self.pause,
            tags=["MT-FREE-AUTO"],
            upload_limit=100000000,
        )

    def load(self):
        for mode in ["adult", "normal"]:
            for torrent_id in self.search(mode):
                torrent_link = self.get_torrent(torrent_id)
                self.add_torrent(torrent_link)


def __main__():
    qb_url = os.environ["QB_URL"]
    if qb_url:
        raise Exception("Miss QB_URL")
    qb_user = os.environ["QB_USER"]
    if qb_user:
        raise Exception("Miss QB_USER")
    qb_password = os.environ["QB_PASSWORD"]
    if qb_password:
        raise Exception("Miss QB_PASSWORD")
    qb_port = os.environ["QB_PORT"]
    if qb_port:
        raise Exception("Miss QB_PORT")
    mt_base_url = os.environ["MT_BASE_URL"]
    if mt_base_url:
        raise Exception("Miss MT_BASE_URL")
    mt_api_key = os.environ["MT_API_KEY"]
    if mt_api_key:
        raise Exception("Miss MT_API_KEY")
    MTFreeAutoTask(
        qb_url, qb_user, qb_password, int(qb_port), mt_base_url, mt_api_key
    ).load()
