import json
from playwright.sync_api import sync_playwright
from learning.browser import read_search
from learning.store import Store

CARD='01:15\n24\n广州领养小猫 #猫咪\n@测试作者\n3周前'

def test_collection_label_before_duration():
    from learning.video_metadata import search_text_fields
    fields=search_text_fields('合集\n'+CARD)
    assert fields['metrics']['digg_count']['value']==24
    assert fields['duration_seconds']==75
    assert not search_text_fields('图文\n'+CARD)

def test_link_fallback_extracts_metadata_without_guessing_caption_numbers():
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True,channel='chromium');page=b.new_page()
        page.set_content('<a href="https://www.douyin.com/video/12345">'+CARD.replace('\n','<br>')+'</a><a href="https://www.douyin.com/video/23456">2026年领养24只猫</a>')
        rows=read_search(page)
        assert rows[0]['metrics']['digg_count']['value']==24
        assert rows[0]['duration_seconds']==75
        assert rows[0]['title']=='广州领养小猫 #猫咪'
        assert not rows[1].get('metrics')
        b.close()

def test_history_repair_preserves_snapshots_and_existing_metrics(tmp_path):
    path=tmp_path/'data.db';store=Store(path)
    task=store.create_task('测试','live')
    store.finish(task['id'],{'videos':[{'id':'12345','title':CARD,'metrics':{'comment_count':{'value':7}}}]},'success','完成')
    imported=store.create_task('导入','import')
    store.finish(imported['id'],{'videos':[{'id':'23456','title':CARD}]},'success','完成')
    store=Store(path)
    row=store.result(task['id'])['videos'][0]
    assert row['metrics']['digg_count']['value']==24
    assert row['metrics']['digg_count']['observed_at']==task['created_at']
    assert row['metrics']['comment_count']['value']==7
    assert row['search_card_text']==CARD
    assert row['title']=='广州领养小猫 #猫咪'
    assert store.result(imported['id'])['videos'][0]['title']==CARD
    assert Store(path).result(task['id'])['videos'][0]==row
