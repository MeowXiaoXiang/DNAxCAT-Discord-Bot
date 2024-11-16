import requests
from bs4 import BeautifulSoup
import re

# 設定論壇的基本網址
forum_base = "https://dnaxcattalk.dnaxcat.com.tw/"

# 定義固定的板塊資訊
forums = {
    "2": {"name": "喵窩站務", "link": f"{forum_base}forum-2-1.html"},
    "52": {"name": "喵窩活動特區", "link": f"{forum_base}forum-52-1.html"},
    "4": {"name": "喵窩周邊快報", "link": f"{forum_base}forum-4-1.html"},
    "3": {"name": "喵窩開發處", "link": f"{forum_base}forum-3-1.html"},
}

def fetch_author_avatar(author_url):
    """抓取作者頭貼圖片"""
    print(f"  正在抓取作者頭貼：{author_url}")
    response = requests.get(author_url)
    if response.status_code != 200:
        print(f"  無法連接到作者頁面：{author_url}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    avatar_tag = soup.select_one("div#uhd .icn.avt img")  # 假設頭貼位於此位置
    if avatar_tag and "src" in avatar_tag.attrs:
        avatar_url = avatar_tag["src"]
        # 確保頭貼連結完整
        return avatar_url if avatar_url.startswith("http") else forum_base + avatar_url
    return None

def fetch_post_time(thread_url):
    """深入文章頁面抓取發佈時間"""
    print(f"  正在抓取文章時間：{thread_url}")
    response = requests.get(thread_url)
    if response.status_code != 200:
        print(f"  無法連接到文章頁面：{thread_url}")
        return "未知"

    soup = BeautifulSoup(response.text, "html.parser")
    time_tag = soup.find("em", id=re.compile(r"authorposton\d+"))
    
    if time_tag:
        # 優先抓取 span 的 title 屬性時間
        span_tag = time_tag.find("span")
        if span_tag and span_tag.has_attr("title"):
            return span_tag["title"]
        
        # 如果沒有 title 屬性，抓取文字內容
        time_text = time_tag.get_text(strip=True).replace("發表於 ", "")
        return time_text
    return "未知"

def fetch_threads(forum_url):
    """抓取指定板塊的文章資訊"""
    print(f"正在連接到板塊：{forum_url}")
    response = requests.get(forum_url)
    if response.status_code != 200:
        print(f"無法連接到板塊：{forum_url}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    threads = []
    threadlist = soup.select("div#threadlist div.bm_c table#threadlisttableid tbody")
    
    for idx, thread in enumerate(threadlist, start=1):
        thread_id = thread.get("id", "")
        if thread_id.startswith("stickthread_"):
            top_status = "置頂"
        elif thread_id.startswith("normalthread_"):
            top_status = "非置頂"
        else:
            continue

        title_tag = thread.find("a", class_="s xst")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = forum_base + title_tag["href"]
        article_id = re.search(r"thread-(\d+)-", link).group(1)

        category_tag = thread.find("em").find("a") if thread.find("em") else None
        category_name = category_tag.get_text(strip=True) if category_tag else "無"
        category_link = forum_base + category_tag["href"] if category_tag else None

        author_tag = thread.find("td", class_="by").find("cite").find("a")
        author_name = author_tag.get_text(strip=True) if author_tag else "未知"
        author_url = forum_base + author_tag["href"] if author_tag else None

        avatar_url = fetch_author_avatar(author_url) if author_url else None
        post_time = fetch_post_time(link)  # 抓取文章詳細時間

        threads.append({
            "article_id": article_id,
            "title": title,
            "link": link,
            "category_name": category_name,
            "category_link": category_link,
            "author": author_name,
            "author_url": author_url,
            "avatar_url": avatar_url,  # 新增的頭貼連結
            "post_time": post_time,
            "top_status": top_status,
        })

        print(f"[{idx}] 抓取文章：{title} (文章ID: {article_id})")

    return threads

# 主程序
print("可用板塊列表：")
for forum_id, forum_info in forums.items():
    print(f"ID: {forum_id}, 板塊名稱: {forum_info['name']}")

chosen_id = input("請輸入要爬取的板塊ID：")
if chosen_id in forums:
    forum_url = forums[chosen_id]["link"]
    forum_name = forums[chosen_id]["name"]
    print(f"開始抓取板塊：{forum_name}")
    
    threads = fetch_threads(forum_url)
    print("\n抓取結果：")
    for thread in threads:
        print(f"文章ID (article_id): {thread['article_id']}")
        print(f"標題 (title): {thread['title']}")
        print(f"發佈時間 (post_time): {thread['post_time']}")
        print("作者資訊 (author):")
        print(f"  名稱 (name): {thread['author']}")
        print(f"  連結 (url): {thread['author_url'] if thread['author_url'] else '無'}")
        print(f"  頭貼 (avatar): {thread['avatar_url'] if thread['avatar_url'] else '無'}")
        print("分類資訊 (category):")
        print(f"  名稱 (name): {thread['category_name']}")
        print(f"  連結 (url): {thread['category_link'] if thread['category_link'] else '無'}")
        print("板塊資訊 (forum):")
        print(f"  ID (id): {chosen_id}")
        print(f"  名稱 (name): {forum_name}")
        print(f"  連結 (url): {forum_url}")
        print(f"文章連結 (url): {thread['link']}")
        print(f"置頂狀態 (top_status): {'是 (true)' if thread['top_status'] == '置頂' else '否 (false)'}")
        print("-" * 40)
else:
    print("無效的板塊ID。")
