import requests
from bs4 import BeautifulSoup

# 設定首頁網址
base_url = "https://dnaxcattalk.dnaxcat.com.tw/forum.php"
forum_base = "https://dnaxcattalk.dnaxcat.com.tw/"

def get_forums(base_url):
    """從首頁抓取所有板塊名稱和對應的連結"""
    response = requests.get(base_url)
    if response.status_code != 200:
        print("無法連接到首頁")
        return {}

    soup = BeautifulSoup(response.text, "html.parser")
    forums = {}

    # 抓取所有板塊名稱和連結
    for link in soup.select(".fl_tb h2 a"):
        forum_name = link.get_text(strip=True)
        forum_link = link['href']
        forum_id = forum_link.split('-')[1]  # 假設ID在連結中第二部分
        forums[forum_id] = {"name": forum_name, "link": forum_base + forum_link}

    return forums

def fetch_author_avatar(author_url):
    """抓取作者的頭貼實際連結"""
    response = requests.get(author_url, allow_redirects=True)  # 允許跳轉到實際的頭貼連結
    if response.status_code != 200:
        print("無法連接到作者頁面")
        return None
    
    soup = BeautifulSoup(response.text, "html.parser")
    avatar_tag = soup.select_one("div#uhd .icn.avt img")
    if avatar_tag and "src" in avatar_tag.attrs:
        avatar_url = avatar_tag["src"]
        if avatar_url.startswith("http"):  # 確保完整的 URL
            return avatar_url
        else:
            return forum_base + avatar_url
    return None

def fetch_threads(forum_url):
    """從指定板塊中抓取所有公告和普通條目"""
    response = requests.get(forum_url)
    if response.status_code != 200:
        print("無法連接到指定板塊")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    threads = []

    # 抓取公告（stickthread_ 開頭）和普通條目（normalthread_ 開頭）
    threadlist = soup.select("div#threadlist div.bm_c table#threadlisttableid tbody")
    
    for thread in threadlist:
        thread_id = thread.get("id", "")
        
        if thread_id.startswith("stickthread_"):
            category = "訂選公告"
        elif thread_id.startswith("normalthread_"):
            category = "普通貼文"
        else:
            continue  # 跳過非目標的條目

        # 標題和連結
        title_tag = thread.find("a", class_="s xst")
        title = title_tag.get_text(strip=True)
        link = forum_base + title_tag["href"]
        
        # 作者和頭貼
        author_tag = thread.find("td", class_="by").find("cite").find("a")
        author_name = author_tag.get_text(strip=True) if author_tag else "未知"
        author_url = forum_base + author_tag["href"] if author_tag else None
        avatar_url = fetch_author_avatar(author_url) if author_url else None  # 抓取頭貼連結

        # 發布時間
        time_tag = thread.find("td", class_="by").find("em")
        post_time = time_tag.get_text(strip=True) if time_tag else "未知"

        # 儲存結果
        threads.append({
            "title": title,
            "link": link,
            "author": author_name,
            "author_url": author_url,
            "avatar_url": avatar_url,
            "post_time": post_time,
            "category": category
        })

    return threads

# 主程序
forums = get_forums(base_url)

# 列出所有板塊名稱和 ID
print("可用板塊列表：")
for forum_id, forum_info in forums.items():
    print(f"ID: {forum_id}, 板塊名稱: {forum_info['name']}")

# 讓使用者輸入板塊 ID
chosen_id = input("請輸入要爬取的板塊ID：")

# 驗證輸入並抓取指定板塊的內容
if chosen_id in forums:
    forum_url = forums[chosen_id]["link"]
    threads = fetch_threads(forum_url)
    for thread in threads:
        print(f"分類：{thread['category']}")
        print(f"標題：{thread['title']}")
        print(f"連結：{thread['link']}")
        print(f"作者：{thread['author']}")
        print(f"頭貼連結：{thread['avatar_url']}")
        print(f"發佈時間：{thread['post_time']}")
        print("-" * 40)
else:
    print("無效的板塊ID。")
