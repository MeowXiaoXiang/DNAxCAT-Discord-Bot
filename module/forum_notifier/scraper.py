# module/forum_notifier/scraper.py

import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
import json
import os
from loguru import logger

class Scraper:
    def __init__(self, base_url, forum_settings=None):
        self.base_url = base_url
        self.session = None
        self.forum_settings = forum_settings
        self.forum_id_to_name = {}
        if forum_settings:
            self._initialize_forum_mapping(forum_settings)

    def _initialize_forum_mapping(self, forum_settings):
        """初始化板塊 ID 與名稱的映射"""
        forums = forum_settings.get('forums', {})
        for forum_name, forum_url in forums.items():
            match = re.search(r'forum-(\d+)-', forum_url)
            if match:
                forum_id = match.group(1)
                self.forum_id_to_name[forum_id] = forum_name
                logger.debug(f"已設定板塊：{forum_name}（ID：{forum_id}）")
            else:
                logger.warning(f"無法從網址中提取板塊ID：{forum_url}")

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        logger.debug("已建立 aiohttp ClientSession")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
        logger.debug("已關閉 aiohttp ClientSession")

    async def FetchThreadIDs(self, forum_settings):
        """抓取所有板塊的文章 ID 列表"""
        tasks = [self._fetch_forum_threads(forum_name, forum_url)
                 for forum_name, forum_url in forum_settings.get('forums', {}).items()]
        logger.info("開始並行抓取所有板塊的文章ID")
        forum_results = await asyncio.gather(*tasks)
        logger.debug(f"所有板塊文章ID抓取結果: {forum_results}")
        return {forum_id: threads for forum_id, threads in forum_results if forum_id}

    async def _fetch_forum_threads(self, forum_name, forum_url):
        """抓取單個板塊的文章 ID 列表"""
        forum_id = self._extract_forum_id(forum_url)
        if not forum_id:
            return None, None

        full_url = self.base_url + forum_url
        logger.info(f"正在抓取板塊：{forum_name}（ID：{forum_id}），網址：{full_url}")

        try:
            async with self.session.get(full_url) as response:
                if response.status != 200:
                    logger.error(f"無法連接到板塊：{full_url}，狀態碼：{response.status}")
                    return forum_id, {'stickthread': [], 'normalthread': []}

                soup = BeautifulSoup(await response.text(), "html.parser")
                threads = self._extract_thread_ids(soup)
                logger.debug(f"板塊 {forum_name}（ID：{forum_id}）文章ID提取結果: {threads}")
                logger.info(f"完成抓取板塊：{forum_name}（ID：{forum_id}）")
                return forum_id, threads

        except Exception as e:
            logger.exception(f"抓取板塊時發生錯誤：{e}")
            return forum_id, {'stickthread': [], 'normalthread': []}

    def _extract_forum_id(self, forum_url):
        """從 URL 中提取板塊 ID"""
        match = re.search(r'forum-(\d+)-', forum_url)
        if match:
            logger.debug(f"從網址 {forum_url} 提取到板塊ID：{match.group(1)}")
            return match.group(1)
        logger.error(f"無法從網址中提取板塊ID：{forum_url}")
        return None

    def _extract_thread_ids(self, soup):
        """從板塊頁面提取文章 ID 列表"""
        threads = {'stickthread': [], 'normalthread': []}
        threadlist = soup.select("div#threadlist div.bm_c table#threadlisttableid tbody[id^='stickthread_'], div#threadlist div.bm_c table#threadlisttableid tbody[id^='normalthread_']")

        normalthread_count = 0
        logger.debug(f"找到 {len(threadlist)} 個文章元素")
        for thread in threadlist:
            thread_id = thread.get("id", "")
            category = 'stickthread' if thread_id.startswith("stickthread_") else 'normalthread'
            if category == 'normalthread' and normalthread_count >= 10:
                logger.debug("已達到非置頂文章數量限制（10篇），跳過剩餘貼文")
                continue

            article_id = self._extract_article_id(thread_id)
            if article_id:
                threads[category].append(article_id)
                if category == 'normalthread':
                    normalthread_count += 1
            logger.debug(f"提取文章ID：{article_id}, 分類：{category}")

        return threads

    def _extract_article_id(self, thread_id):
        """從 thread_id 中提取文章 ID"""
        match = re.search(r'_(\d+)', thread_id)
        if match:
            logger.debug(f"從 thread_id {thread_id} 提取到文章ID：{match.group(1)}")
            return match.group(1)
        logger.warning(f"無法從 thread_id 中提取文章ID：{thread_id}")
        return None

    async def FetchThreadDetail(self, forum_id, thread_id):
        """抓取指定文章的詳細資訊"""
        try:
            category_info = await self._fetch_category_info(forum_id, thread_id)
            logger.debug(f"提取分類資訊：{category_info}")
            thread_url = f"{self.base_url}thread-{thread_id}-1-1.html"
            return await self._fetch_thread_detail_page(thread_url, forum_id, thread_id, category_info)

        except Exception as e:
            logger.exception(f"抓取文章時發生錯誤：{e}")
            return {}

    async def _fetch_category_info(self, forum_id, thread_id):
        """從板塊頁面提取文章的分類資訊"""
        forum_url = f"{self.base_url}forum-{forum_id}-1.html"
        async with self.session.get(forum_url) as response:
            if response.status != 200:
                logger.error(f"無法連接到板塊頁面：{forum_url}，狀態碼：{response.status}")
                return {"name": "無", "url": None}

            soup = BeautifulSoup(await response.text(), "html.parser")
            thread_tag = soup.find("tbody", id=f"normalthread_{thread_id}") or soup.find("tbody", id=f"stickthread_{thread_id}")
            if thread_tag:
                em_tag = thread_tag.find("em")
                if em_tag:
                    a_tag = em_tag.find("a")
                    if a_tag and "href" in a_tag.attrs:
                        logger.debug(f"找到文章分類：{a_tag.get_text(strip=True)}")
                        return {"name": a_tag.get_text(strip=True), "url": self.base_url + a_tag["href"]}
        logger.debug(f"文章 {thread_id} 無分類資訊")
        return {"name": "無", "url": None}

    async def _fetch_thread_detail_page(self, thread_url, forum_id, thread_id, category_info):
        """抓取文章頁面的詳細資訊"""
        async with self.session.get(thread_url) as response:
            if response.status != 200:
                logger.error(f"無法連接到文章頁面：{thread_url}，狀態碼：{response.status}")
                return {}

            soup = BeautifulSoup(await response.text(), "html.parser")
            title = self._extract_text(soup.find("span", id="thread_subject"))
            post_time = self._extract_post_time(soup)
            author_info = await self._extract_author_info(soup)
            top_status = category_info["name"] == "stickthread"

            logger.debug(f"文章 {thread_id} 詳細資訊：標題-{title}, 時間-{post_time}, 作者-{author_info}")
            return {
                "article_id": thread_id,
                "title": title,
                "post_time": post_time,
                "author": author_info,
                "category": category_info,
                "forum": {
                    "id": forum_id,
                    "name": self.forum_id_to_name.get(forum_id, "未知"),
                    "url": f"{self.base_url}forum-{forum_id}-1.html",
                },
                "url": thread_url,
                "top_status": top_status,
            }

    def _extract_text(self, tag):
        """安全提取文字"""
        text = tag.get_text(strip=True) if tag else "未知"
        logger.debug(f"提取文字：{text}")
        return text

    def _extract_post_time(self, soup):
        """提取文章發佈時間"""
        time_tag = soup.find("em", id=re.compile(r"authorposton\d+"))
        if time_tag:
            span_tag = time_tag.find("span")
            if span_tag and span_tag.has_attr("title"):
                logger.debug(f"提取發佈時間：{span_tag['title']}")
                return span_tag["title"]
            post_time = time_tag.get_text(strip=True).replace("發表於 ", "")
            logger.debug(f"提取發佈時間：{post_time}")
            return post_time
        logger.debug("未能提取發佈時間")
        return "未知"

    async def _extract_author_info(self, soup):
        """提取文章作者資訊"""
        post_div = soup.find("div", id=re.compile(r"post_\d+"))
        if post_div:
            author_tag = post_div.find("a", class_="xw1")
            if author_tag:
                author_url = self.base_url + author_tag["href"]
                author_avatar = await self._fetch_author_avatar(author_url)
                logger.debug(f"作者資訊：{author_tag.get_text(strip=True)}, 頭貼-{author_avatar}")
                return {
                    "name": author_tag.get_text(strip=True),
                    "url": author_url,
                    "avatar": author_avatar,
                }
        logger.debug("未能提取作者資訊")
        return {"name": "未知", "url": None, "avatar": None}

    async def _fetch_author_avatar(self, author_url):
        """抓取作者頭像"""
        async with self.session.get(author_url) as response:
            if response.status != 200:
                logger.error(f"無法連接到作者頁面：{author_url}，狀態碼：{response.status}")
                return None
            soup = BeautifulSoup(await response.text(), "html.parser")
            avatar_tag = soup.select_one("div#uhd .icn.avt img")
            if avatar_tag and "src" in avatar_tag.attrs:
                avatar_url = avatar_tag["src"]
                full_url = avatar_url if avatar_url.startswith("http") else self.base_url + avatar_url
                logger.debug(f"抓取作者頭像：{full_url}")
                return full_url
        logger.debug("未能提取作者頭像")
        return None

if __name__ == "__main__":
    async def main():
        forum_settings = {
            "base_url": "https://dnaxcattalk.dnaxcat.com.tw/",
            "forums": {
                "喵窩站務": "forum-2-1.html",
                "喵窩活動特區": "forum-52-1.html",
                "喵窩周邊快報": "forum-4-1.html",
                "喵窩開發處": "forum-3-1.html"
            }
        }

        # 檢查並建立 test 資料夾
        if not os.path.exists('test'):
            os.makedirs('test')
            logger.info("已建立 'test' 資料夾")
        else:
            logger.info("'test' 資料夾已存在")

        async with Scraper(forum_settings["base_url"], forum_settings) as scraper:
            thread_ids = await scraper.FetchThreadIDs(forum_settings)
            with open('test/thread_ids.json', 'w', encoding='utf-8') as f:
                json.dump(thread_ids, f, ensure_ascii=False, indent=4)

            for forum_id, threads in thread_ids.items():
                for thread_id in threads['normalthread'][:1]:  # 測試一篇文章
                    thread_detail = await scraper.FetchThreadDetail(forum_id, thread_id)
                    with open('test/thread_detail.json', 'w', encoding='utf-8') as f:
                        json.dump(thread_detail, f, ensure_ascii=False, indent=4)

    asyncio.run(main())
