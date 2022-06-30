# -*- encoding : utf-8 -*-
import re
import copy
import json
import random
import string
import pymongo
from typing import List, Dict
from dataclass import Match
from khl.command import Lexer
from khl.requester import HTTPRequester
from khl import Bot, Message, Cert, User
from khl.card import Module, Card, Struct, Element, Types, CardMessage


# webhook
# cert = Cert(token='', verify_token='')
# bot = Bot(cert=cert, port=3000, route='/webhook')

# websocket
bot = Bot(token='')


dbclient = pymongo.MongoClient("mongodb://localhost:27017/")
db = dbclient['hll_match']
matches = db['matches']
cards = db['cards']
msg_ids = db['msg_ids']
configs = db['config']
# config json in mongodb config connection
# {
#     "guild": "",
#     "main_channel": "",
#     "master": "",
#     "channels": [],
#     "parent_id": "",
#     "edit_permission": [],
#     "bind_channel_permission": {}
# }


class KeyWord(Lexer):
    keyword: str
    start_with: bool
    no_space: bool

    def __init__(self, keyword: str, start_with: bool = True, no_space: bool = False):
        self.keyword = keyword
        self.start_with = start_with
        self.no_space = no_space

    def lex(self, msg: Message) -> List[str]:
        if self.no_space:
            command = msg.content.split('\n')[0].strip()
            if command != self.keyword:
                raise Lexer.NotMatched(msg)
        elif self.start_with:
            command = msg.content.split(' ')[0].strip()
            if command != self.keyword:
                raise Lexer.NotMatched(msg)
        else:
            if msg.content.find(self.keyword) < 0:
                raise Lexer.NotMatched(msg)
        return []


async def list_to_str_list(value):
    return [str(i) for i in value]

async def random_id(num: int) -> str:
    return ''.join(random.sample(string.ascii_letters + string.digits, num))


async def text_parser(text: str, roles_id_name: dict):
    try:
        name = re.findall(r'(?:\\\(name\\\)|\(name\))(.*)(?:\\\(name\\\)|\(name\))', text)[0]
        role1_r = re.findall(r'(?:\\\(role1\\\)|\(role1\))(.*)(?:\\\(role1\\\)|\(role1\))', text)[0]
        role2_r = re.findall(r'(?:\\\(role2\\\)|\(role2\))(.*)(?:\\\(role2\\\)|\(role2\))', text)[0]
        role1 = await list_to_str_list(re.findall(r'(?:\(rol\)|\\\(rol\\\))(\d+)(?:\(rol\)|\\\(rol\\\))', role1_r))
        role2 = await list_to_str_list(re.findall(r'(?:\(rol\)|\\\(rol\\\))(\d+)(?:\(rol\)|\\\(rol\\\))', role2_r))
        role1 = ';'.join(role1)
        role2 = ';'.join(role2)
        if len(role1) == 0:
            role1 = role1_r.strip()
        if len(role2) == 0:
            role2 = role2_r.strip()
        match_time = re.findall(r'(?:\\\(time\\\)|\(time\))(.*)(?:\\\(time\\\)|\(time\))', text)[0]
        map_name = re.findall(r'(?:\\\(map\\\)|\(map\))(.*)(?:\\\(map\\\)|\(map\))', text)[0]
        score = re.findall(r'(?:\\\(score\\\)|\(score\))(.*)(?:\\\(score\\\)|\(score\))', text)[0]
    except IndexError:
        return None
    while True:
        match_id = await random_id(8)
        if len(list(matches.find({'match_id': match_id}))) == 0:
            break
    channel_id = await create_channel(role1, role2, roles_id_name)
    return Match(match_id, name, role1, role2, match_time, map_name, score, channel_id)


async def khl_text_to_data(texts: str) -> List[Match]:
    roles_id_name = await get_roles_id_name()
    texts = texts.split('\\-\\--')
    datas = []
    for text in texts:
        text = text.strip()
        datas.append((await text_parser(text, roles_id_name)))
    return datas


async def match_dict_to_object(match_dict: dict) -> Match:
    return Match(match_dict['_id'],
                 match_dict['name'],
                 match_dict['role1'],
                 match_dict['role2'],
                 match_dict['match_time'],
                 match_dict['map_name'],
                 match_dict['score'],
                 match_dict['channel'])


async def match_dicts_to_objects(match_dicts: List[Dict]) -> List[Match]:
    data = []
    for match_dict in match_dicts:
        data.append(await match_dict_to_object(match_dict))
    return data


async def match_objects_to_dicts(match_objects: List[Match]) -> List[Dict]:
    data = []
    for match_object in match_objects:
        data.append(match_object.todict())
    return data


async def save_match_object(data: Match):
    matches.insert_one(data.todict())


async def save_match_objects(data: List[Match]):
    matches.insert_many(await match_objects_to_dicts(data))


async def match_ids_to_objects(ids: List[str]) -> List[Match]:
    match_dicts = []
    for i in ids:
        match_dict = matches.find_one({'_id': i})
        if match_dict is None:
            continue
        match_dicts.append(dict(match_dict))
    match_objects = await match_dicts_to_objects(match_dicts)
    return match_objects


async def generate_match_kmd_text(data: Match, need_id: bool = False) -> str:
    role1 = data.role1 if data.role1.find(";") < 0 else data.role1.replace(";", "(rol) (rol)")
    role2 = data.role2 if data.role2.find(";") < 0 else data.role2.replace(";", "(rol) (rol)")
    text = f'**{data.name}**\n' \
           f'(rol){role1}(rol) vs (rol){role2}(rol)\n' \
           f'> {data.match_time}\n' \
           f'地图: {data.map_name}\n' \
           f'得分: (spl){data.score}(spl)\n\n' \
           f'(chn){data.channel}(chn)'
    if need_id:
        text += f'\nID: {data.id}'
    return text


async def generate_match_card_from_match_objects(data: List[Match], preview: bool = False, header: str = '赛事对象预览',
                                                 logo: str = 'https://img.kaiheila.cn/assets/2020-01/tMONHxmVhk03k03k.png/icon',
                                                 source_card_id: str = '', channel: str = '',) -> [Card, str]:
    if len(source_card_id) == 0:
        card_id = await random_id(12)
    else:
        card_id = source_card_id
    match_ids = []
    c = Card()
    if len(logo) != 0:
        c.append(Module.Section(
            accessory=Element.Image(logo, circle=True, alt='left', size=Types.Size.SM),
            text=Element.Text(f'**{header}**', type=Types.Text.KMD)
        ))
    else:
        c.append(Module.Header(header))
    if preview:
        c.append(Module.Section(f'卡片ID： {card_id}'))
        if channel != 0:
            c.append(Module.Section(Element.Text(f'频道： (chn){channel}(chn)', type=Types.Text.KMD)))
    c.append(Module.Divider())
    pdata = []
    count = 0
    need_id = False
    for i in data:
        count += 1
        if preview:
            need_id = True
        match_ids.append(i.id)
        pdata.append(Element.Text(await generate_match_kmd_text(i, need_id=need_id), type=Types.Text.KMD))
        if count >= 3:
            c.append(Module.Section(Struct.Paragraph(3, *pdata)))
            count = 0
            pdata.clear()
    if count != 0:
        c.append(Module.Section(Struct.Paragraph(len(pdata), *pdata)))
    if not preview:
        c.append(Module.Divider())
        c.append(Module.Context(f'卡片ID： {card_id}'))
    if len(source_card_id) == 0:
        cards.insert_one({'_id': card_id, 'matches': match_ids, 'preview': preview, 'header': header, 'logo': logo})
    return c, card_id


async def generate_match_card_from_card_id(card_id: str) -> [Card, str]:
    card_info = cards.find_one({'_id': card_id})
    if card_info is None:
        return Card(Module.Section('卡片未找到'), color='#B22222'), ''
    match_objects = await match_ids_to_objects(card_info['matches'])
    if 'channel' not in card_info:
        channel = ''
    else:
        channel = card_info['channel']
    card, _ = await generate_match_card_from_match_objects(match_objects, card_info['preview'], card_info['header'],
                                                           card_info['logo'], source_card_id=card_id, channel=channel)
    return card, card_id


async def generate_match_card_from_card_id_with_channel(card_id: str) -> [Card, str, str]:
    card_info = cards.find_one({'_id': card_id})
    if card_info is None:
        return Card(Module.Section('卡片未找到'), color='#B22222'), ''
    match_objects = await match_ids_to_objects(card_info['matches'])
    if 'channel' not in card_info:
        channel = ''
    else:
        channel = card_info['channel']
    card, _ = await generate_match_card_from_match_objects(match_objects, card_info['preview'], card_info['header'],
                                                           card_info['logo'], source_card_id=card_id, channel=channel)
    return card, card_id, channel


async def get_roles_id_name():
    config = dict(configs.find_one())
    guild = await bot.fetch_guild(config['guild'])
    roles = await guild.fetch_roles()
    roles_id_name = {}
    for i in roles:
        roles_id_name[str(i.id)] = i.name
    return roles_id_name


async def get_role1_role2_name(role1: str, role2: str):
    roles_id_name = await get_roles_id_name()
    role1, role2 = await get_role1_role2_name_with_cached_all_id_name(role1, role2, roles_id_name)
    return role1, role2


async def get_role1_role2_name_with_cached_all_id_name(role1: str, role2: str, roles_id_name: dict):
    if role1.find(';') >= 0:
        role1s = role1.split(';')
        role1s_names = []
        for i in role1s:
            if i in roles_id_name:
                role1s_names.append(roles_id_name[i])
            else:
                role1s_names.append('角色不存在')
        role1 = ';'.join(role1s_names)
    else:
        if role1 in roles_id_name:
            role1 = roles_id_name[role1]
        else:
            role1 = '角色不存在'
    if role2.find(';') >= 0:
        role2s = role2.split(';')
        role2s_names = []
        for i in role2s:
            if i in roles_id_name:
                role2s_names.append(roles_id_name[i])
            else:
                role2s_names.append('角色不存在')
        role2 = ';'.join(role2s_names)
    else:
        if role2 in roles_id_name:
            role2 = roles_id_name[role2]
        else:
            role2 = '角色不存在'
    return role1, role2


async def create_channel(role1: str, role2: str, roles_id_name=None) -> str:
    if roles_id_name is not None:
        role1, role2 = await get_role1_role2_name_with_cached_all_id_name(role1, role2, roles_id_name)
    else:
        role1, role2 = await get_role1_role2_name(role1, role2)
    channel_name = f'{role1}-vs-{role2}-{await random_id(4)}'
    config = dict(configs.find_one())
    data = {'guild_id': config['guild'], 'parent_id': config['parent_id'], 'name': channel_name}
    channel_id = (await bot.client.gate.request('POST', 'channel/create', data=data))['id']
    return channel_id


async def get_channel_name(channel_id: str) -> str:
    return (await bot.fetch_public_channel(channel_id)).name


async def generate_all_public_channel_match_card_from_card_id(card_id: str):
    card_info = cards.find_one({'_id': card_id})
    match_objects = await match_ids_to_objects(card_info['matches'])
    logo = card_info['logo']
    preview = card_info['preview']
    header = card_info['header']
    c = Card()
    if len(logo) != 0:
        c.append(Module.Section(
            accessory=Element.Image(logo, circle=True, alt='left', size=Types.Size.SM),
            text=Element.Text(f'**{header}**', type=Types.Text.KMD)
        ))
    else:
        c.append(Module.Header(header))
    if preview:
        c.append(Module.Section(f'卡片ID： {card_id}'))
    c.append(Module.Divider())
    pdata = []
    count = 0
    need_id = False
    roles_id_name = await get_roles_id_name()
    for i in match_objects:
        count += 1
        if preview:
            need_id = True
        role1, role2 = await get_role1_role2_name_with_cached_all_id_name(i.role1, i.role2, roles_id_name)
        text = (await generate_match_kmd_text(i, need_id=need_id)).replace('(rol) (rol)', ';').replace('(rol)', '').replace('(chn)', '')
        channel_name = await get_channel_name(i.channel)
        text = text.replace(i.role1, role1).replace(i.role2, role2).replace(i.channel, f'#{channel_name}')
        pdata.append(Element.Text(text, type=Types.Text.KMD))
        if count >= 3:
            c.append(Module.Section(Struct.Paragraph(3, *pdata)))
            count = 0
            pdata.clear()
    if count != 0:
        c.append(Module.Section(Struct.Paragraph(len(pdata), *pdata)))
    if not preview:
        c.append(Module.Divider())
        c.append(Module.Context(f'卡片ID： {card_id}'))
    return c


async def get_guild_master_id(guild_id: str) -> str:
    return (await bot.fetch_guild(guild_id)).master_id


async def check_edit_permission(guild_id: str, user_id: str) -> bool:
    config = dict(configs.find_one())
    if user_id == config['master']:
        return True
    if guild_id != config['guild']:
        return False
    if (await get_guild_master_id(guild_id)) == user_id:
        return True
    if user_id in config['edit_permission']:
        return True
    return False


async def check_bind_other_permission(guild_id: str, user_id: str) -> bool:
    if (await get_guild_master_id(guild_id)) == user_id:
        return True
    config = dict(configs.find_one())
    if guild_id == config['guild']:
        if user_id in config['edit_permission']:
            return True
    else:
        if guild_id not in config['bind_channel_permission']:
            return False
        if user_id in config['bind_channel_permission'][guild_id]:
            return True
    return False


async def get_user(user_id: str) -> User:
    return await bot.fetch_user(user_id)


@bot.command(lexer=KeyWord(keyword='.赛事对象生成', no_space=True))
async def generate_match(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    match_datas = await khl_text_to_data(msg.content.replace('.赛事对象生成', '').strip())
    await save_match_objects(match_datas)
    preview_card, card_id = await generate_match_card_from_match_objects(match_datas, preview=True)
    msg_id = (await msg.reply(CardMessage(preview_card)))['msg_id']
    if len(card_id) != 0:
        msg_ids.insert_one({'_id': msg_id, 'card_id': card_id})


@bot.command(lexer=KeyWord(keyword='.赛事对象列表'))
async def list_match_objects(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    n = 0
    text = '---\n'
    match_objects = matches.find({})
    c = Card(Module.Header('赛事对象列表'))
    for match_object in match_objects:
        n += 1
        match_id = match_object['_id']
        match_name = match_object['name']
        match_time = match_object['match_time']
        role1, role2 = match_object['role1'], match_object['role2']
        role1 = role1 if role1.find(";") < 0 else role1.replace(";", "(rol) (rol)")
        role2 = role2 if role2.find(";") < 0 else role2.replace(";", "(rol) (rol)")
        match_map = match_object['map_name']
        match_score = match_object['score']
        channel = match_object['channel']
        text1 = f'{n}. ID: {match_id}\n' \
                f'  - 名称: {match_name}\n' \
                f'  - 角色: (rol){role1}(rol) vs (rol){role2}(rol)\n' \
                f'  - 时间: {match_time}\n' \
                f'  - 地图: {match_map}\n' \
                f'  - 得分 {match_score}\n' \
                f'  - 频道 (chn){channel}(chn)\n---\n'
        if len(json.dumps(text + text1)) + 42 + 145 > 5000:
            c.append(Module.Section(Element.Text(text, type=Types.Text.KMD)))
            text = ''
        if len(c.__dict__['_modules']) == 5:
            text = ''
            await msg.reply(CardMessage(c))
            c = Card(Module.Header('赛事对象列表'))
        text += text1
    c.append(Module.Section(Element.Text(text, type=Types.Text.KMD)))
    await msg.reply(CardMessage(c))


@bot.command(lexer=KeyWord(keyword='.赛事对象删除', start_with=False))
async def del_match_objects_from_match_ids(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    arg = re.sub(r'(?:\(met\)(?:.*)\(met\))?(?:.*)\.赛事对象删除', '', msg.content, count=0).strip()
    match_ids = arg.strip().split(' ')
    if len(match_ids) == 0:
        await msg.reply('赛事对象ID为空')
        return
    r = matches.delete_many({'_id': {'$in': match_ids}})
    await msg.reply(f'{r.deleted_count} 个对象已删除')


@bot.command(lexer=KeyWord(keyword='.赛事对象全部清空'))
async def clean_all_match_objects(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    r = matches.delete_many({})
    await msg.reply(f'{r.deleted_count} 个对象已删除')


@bot.command(lexer=KeyWord(keyword='.赛事卡片生成', start_with=False))
async def generate_match_card_form_card_id(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    arg = re.sub(r'(?:\(met\)(?:.*)\(met\))?(?:.*)\.赛事卡片生成', '', msg.content, count=0).strip()
    if 'quote' in msg.extra:
        msg_id = msg.extra['quote']['rong_id']
        result = msg_ids.find_one({'_id': msg_id})
        if result is None:
            await msg.reply('没有找到消息对应卡片ID')
            return
        card_id = result['card_id']
        card = cards.find_one({'_id': card_id})
        if card is None:
            await msg.reply('没有找到该卡片')
            return
    else:
        card_id = arg.strip()
        card = cards.find_one({'_id': card_id})
        if card is None:
            await msg.reply('没有找到该卡片')
            return
    card, card_id = await generate_match_card_from_card_id(card_id)
    msg_id = (await msg.reply(CardMessage(card)))['msg_id']
    if len(card_id) != 0:
        msg_ids.insert_one({'_id': msg_id, 'card_id': card_id})


@bot.command(lexer=KeyWord(keyword='.赛事卡片创建', start_with=False))
async def generate_match_card_from_match_ids(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    arg = re.sub(r'(?:\(met\)(?:.*)\(met\))?(?:.*)\.赛事卡片创建', '', msg.content, count=0).strip()
    match_ids = arg.strip().split(' ')
    if len(match_ids) == 0:
        await msg.reply('赛事对象ID为空')
        return
    match_objects = await match_ids_to_objects(match_ids)
    preview_card, card_id = await generate_match_card_from_match_objects(match_objects, preview=True)
    msg_id = (await msg.reply(CardMessage(preview_card)))['msg_id']
    if len(card_id) != 0:
        msg_ids.insert_one({'_id': msg_id, 'card_id': card_id})


@bot.command(lexer=KeyWord(keyword='.赛事卡片删除', start_with=False))
async def del_match_card_from_card_ids(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    arg = re.sub(r'(?:\(met\)(?:.*)\(met\))?(?:.*)\.赛事卡片删除', '', msg.content, count=0).strip()
    cards_ids = arg.strip().split(' ')
    if len(cards_ids) == 0:
        await msg.reply('赛事卡片ID为空')
        return
    r1 = cards.delete_many({'_id': {'$in': cards_ids}})
    r2 = msg_ids.delete_many({'card_id': {'$in': cards_ids}})
    await msg.reply(f'{r1.deleted_count} 个卡片已删除, {r2.deleted_count} 个消息ID已删除')


@bot.command(lexer=KeyWord(keyword='.赛事卡片全部清空'))
async def clean_all_match_cards(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    r1 = cards.delete_many({})
    r2 = msg_ids.delete_many({})
    await msg.reply(f'{r1.deleted_count} 个卡片已删除, {r2.deleted_count} 个消息ID已删除')


@bot.command(lexer=KeyWord(keyword='.消息ID清空'))
async def clean_all_msg_ids(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    r = msg_ids.delete_many({})
    await msg.reply(f'{r.deleted_count} 个消息ID已删除')


# [{"type": "card", "size": "lg", "modules": [{"type": "header", "text": ""}, {"type": "section", "text": {"type": "kmarkdown"}, "mode": "left"}]}]
# 145 字符 中文会转成unicode 一个字符 unicode 7 字符 最多 20_000 字符 一个 section 的 content 里最多 5000 字符
# 赛事卡片列表  42 字符
@bot.command(lexer=KeyWord(keyword='.赛事卡片列表'))
async def list_match_card(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    n = 0
    text = '---\n'
    match_cards = cards.find({})
    c = Card(Module.Header('赛事卡片列表'))
    for match_card in match_cards:
        n += 1
        card_id = match_card['_id']
        match_ids = ', '.join(match_card['matches'])
        if match_card['preview']:
            preview = '开'
        else:
            preview = '关'
        header = match_card['header']
        logo = match_card['logo']
        text1 = f'{n}. ID: {card_id}\n' \
                f'  - 赛事对象ID: {match_ids}\n' \
                f'  - 预览: {preview}\n' \
                f'  - 标题: {header}\n' \
                f'  - logo: {logo}\n'
        if 'channel' in match_card:
            channel = match_card['channel']
            text1 += f'  - 频道: (chn){channel}(chn)\n---\n'
        else:
            text1 += '---\n'
        if len(json.dumps(text + text1)) + 42 + 145 > 5000:
            c.append(Module.Section(Element.Text(text, type=Types.Text.KMD)))
            text = ''
        if len(c.__dict__['_modules']) == 5:
            text = ''
            await msg.reply(CardMessage(c))
            c = Card(Module.Header('赛事卡片列表'))
        text += text1
    c.append(Module.Section(Element.Text(text, type=Types.Text.KMD)))
    await msg.reply(CardMessage(c))


@bot.command(lexer=KeyWord(keyword='.获取卡片ID', start_with=False))
async def get_match_card_id(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    if 'quote' not in msg.extra:
        await msg.reply('请引用/回复消息')
        return
    msg_id = msg.extra['quote']['rong_id']
    result = msg_ids.find_one({'_id': msg_id})
    if result is None:
        await msg.reply('没有找到该卡片')
        return
    card_id = result['card_id']
    await msg.reply(f'卡片ID: {card_id}')


@bot.command(lexer=KeyWord(keyword='.赛事卡片修改', start_with=False))
async def modify_match_card(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    args = re.sub(r'(?:\(met\)(?:.*)\(met\))?(?:.*)\.赛事卡片修改', '', msg.content, count=0).strip()
    if 'quote' in msg.extra:
        msg_id = msg.extra['quote']['rong_id']
        result = msg_ids.find_one({'_id': msg_id})
        if result is None:
            await msg.reply('没有找到消息对应卡片ID')
            return
        card_id = result['card_id']
        card = cards.find_one({'_id': card_id})
        if card is None:
            await msg.reply('没有找到该卡片')
            return
        args = args.strip().split(' ')
        if len(args) < 1:
            await msg.reply('缺少参数')
            return
        while True:
            if len(args) <= 0:
                await msg.reply('没有找到关键词')
            command = args.pop(0).strip()
            if len(command) > 0:
                break
        context = ' '.join(args).strip()
    else:
        args = args.strip().split(' ')
        if len(args) < 2:
            await msg.reply('缺少参数')
            return
        while True:
            if len(args) <= 0:
                await msg.reply('没有找到赛事卡片ID')
            card_id = args.pop(0).strip()
            if len(card_id) > 0:
                break
        card = cards.find_one({'_id': card_id})
        if card is None:
            await msg.reply('没有找到该卡片')
            return
        while True:
            if len(args) <= 0:
                await msg.reply('没有找到关键词')
            command = args.pop(0).strip()
            if len(command) > 0:
                break
        context = ' '.join(args).strip()

    log = '未修改'

    card = dict(card)
    if command == '预览关':
        card['preview'] = False
        log = '预览模式已关闭'
    elif command == '预览开':
        card['preview'] = True
        log = '预览模式已开启'
    elif command == '标题':
        if len(context) == 0:
            await msg.reply('缺少参数')
            return
        card['header'] = context
        log = f'标题已修改为 {context}'
    elif command == 'logo':
        if len(context) == 0:
            await msg.reply('缺少参数')
            return
        else:
            if not context.startswith('https://img.kaiheila.cn') and not context.startswith('https://img.kookapp.cn'):
                await msg.reply('请填写 KOOK 图片链接')
                return
            card['logo'] = context
            log = f'logo 已修改为 {context}'
    elif command == '添加赛事':
        if len(context) == 0:
            await msg.reply('缺少参数')
            return
        match = matches.find_one({'_id': context})
        if match is None:
            await msg.reply('赛事对象未找到')
            return
        card['matches'].append(context)
        log = f'赛事对象 {context} 已添加'
    elif command == '删除赛事':
        if len(context) == 0:
            await msg.reply('缺少参数')
            return
        if context not in card['matches']:
            await msg.reply('赛事对象不存在于该卡片中')
            return
        card['matches'].remove(context)
        log = f'赛事对象 {context} 已删除'
    elif command == '设置频道':
        channel_ids = context.replace('(chn)', '').replace('\\(chn\\)', '').strip().split(' ')
        if len(channel_ids) != 1:
            await msg.reply('缺少参数或参数过多')
            return
        card['channel'] = channel_ids[0]
        log = f'赛事卡片主频道设置为 {context}'
    cards.update_one({'_id': card_id}, {'$set': card})
    await msg.reply(log)


@bot.command(lexer=KeyWord(keyword='.赛事对象修改'))
async def modify_match_object(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    args = re.sub(r'(?:\(met\)(?:.*)\(met\))?(?:.*)\.赛事对象修改', '', msg.content, count=0).strip()
    args = args.strip().split(' ')
    if len(args) < 2:
        await msg.reply('缺少参数')
        return
    while True:
        if len(args) <= 0:
            await msg.reply('没有找到赛事对象ID')
        match_id = args.pop(0).strip()
        if len(match_id) > 0:
            break
    match = matches.find_one({'_id': match_id})
    if match is None:
        await msg.reply('没有找到该赛事')
        return
    while True:
        if len(args) <= 0:
            await msg.reply('没有找到关键词')
        command = args.pop(0).strip()
        if len(command) > 0:
            break
    context = ' '.join(args).strip()

    match = dict(match)
    if command == '频道生成':
        match['channel'] = await create_channel(match['role1'], match['role2'])
        await msg.reply('频道已重新生成')
        return
    if len(args) < 1:
        await msg.reply('缺少参数')
        return
    log = '未修改'
    if command == '名称':
        match['name'] = context
        log = f'赛事对象 名称 修改为 {context}'
    elif command == '角色1':
        data = await list_to_str_list(re.findall(r'(?:\(rol\)|\\\(rol\\\))(\d+)(?:\(rol\)|\\\(rol\\\))', context))
        if len(data) == 0:
            data = context
        match['role1'] = ';'.join(data)
        log = f'赛事对象 角色1 修改为 {context}'
    elif command == '角色2':
        data = await list_to_str_list(re.findall(r'(?:\(rol\)|\\\(rol\\\))(\d+)(?:\(rol\)|\\\(rol\\\))', context))
        if len(data) == 0:
            data = context
        match['role2'] = ';'.join(data)
        log = f'赛事对象 角色2 修改为 {context}'
    elif command == '时间':
        match['match_time'] = context
        log = f'赛事对象 时间 修改为 {context}'
    elif command == '地图':
        match['map_name'] = context
        log = f'赛事对象 地图 修改为 {context}'
    elif command == '得分':
        match['score'] = context
        log = f'赛事对象 得分 修改为 {context}'
    elif command == '频道':
        match['channel'] = context.replace('(chn)', '').replace('\\(chn\\)', '')
        log = f'赛事对象 频道 修改为 {context}'
    matches.update_one({'_id': match_id}, {'$set': match})
    await msg.reply(log)


@bot.command(lexer=KeyWord(keyword='.设置分组'))
async def set_parent_id(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    if msg.ctx.guild.id != config['guild']:
        await msg.reply('此服务器不允许进行此操作')
        return
    parent_id = (await bot.fetch_public_channel(msg.ctx.channel.id)).parent_id
    config['parent_id'] = parent_id
    configs.update_one({'guild': msg.ctx.guild.id}, {'$set': config})
    await msg.reply('已设置分组')


@bot.command(lexer=KeyWord(keyword='.清除分组'))
async def clear_parent_id(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    config['parent_id'] = ''
    configs.update_one({'guild': msg.ctx.guild.id}, {'$set': config})
    await msg.reply('已清除分组')


@bot.command(lexer=KeyWord(keyword='.绑定频道'))
async def bind_channel(msg: Message):
    if not (await check_bind_other_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    config['channels'].append(msg.ctx.channel.id)
    configs.update_one({'guild': config['guild']}, {'$set': config})
    await msg.reply('该频道已绑定')


@bot.command(lexer=KeyWord(keyword='.解绑频道'))
async def unbind_channel(msg: Message):
    if not (await check_bind_other_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    if msg.ctx.channel.id not in config['channels']:
        await msg.reply('该频道未绑定')
        return
    config['channels'].remove(msg.ctx.channel.id)
    configs.update_one({'guild': config['guild']}, {'$set': config})
    await msg.reply('该频道已解绑')


@bot.command(lexer=KeyWord(keyword='.绑定主频道'))
async def bind_main_channel(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    config['main_channel'] = msg.ctx.channel.id
    configs.update_one({'guild': msg.ctx.guild.id}, {'$set': config})
    await msg.reply('主频道已绑定')


@bot.command(lexer=KeyWord(keyword='.统一发送', start_with=False))
async def card_all_channel_send(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    arg = re.sub(r'(?:\(met\)(?:.*)\(met\))?(?:.*)\.统一发送', '', msg.content, count=0).strip()
    if 'quote' in msg.extra:
        msg_id = msg.extra['quote']['rong_id']
        result = msg_ids.find_one({'_id': msg_id})
        if result is None:
            await msg.reply('没有找到消息对应卡片ID')
            return
        card_id = result['card_id']
        card = cards.find_one({'_id': card_id})
        if card is None:
            await msg.reply('没有找到该卡片')
            return
    else:
        card_id = arg.strip()
        card = cards.find_one({'_id': card_id})
        if card is None:
            await msg.reply('没有找到该卡片')
            return
    card, card_id, channel = await generate_match_card_from_card_id_with_channel(card_id)
    config = dict(configs.find_one())
    channel = channel if channel != '' else config['main_channel']
    msg_id = (await (await bot.client.fetch_public_channel(channel)).send(CardMessage(card)))['msg_id']
    if len(card_id) != 0:
        card_msg = CardMessage(await generate_all_public_channel_match_card_from_card_id(card_id))
        msg_ids.insert_one({'_id': msg_id, 'card_id': card_id})
        for i in config['channels']:
            await (await bot.fetch_public_channel(i)).send(card_msg)


@bot.command(lexer=KeyWord(keyword='.编辑权限添加'))
async def add_edit_permission(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    users = msg.extra['mention']
    if len(users) == 0:
        await msg.reply('请at需要添加的用户')
        return
    config = dict(configs.find_one())
    for i in users:
        user_id = str(i)
        if user_id in config['edit_permission']:
            continue
        else:
            config['edit_permission'].append(user_id)
    configs.update_one({'guild': msg.ctx.guild.id}, {'$set': config})
    names = ''
    for i in users:
        user = await get_user(str(i))
        names += f'{user.username}#{user.identify_num}, '
    names = names[:-2]
    await msg.reply(f'已添加用户 {names} 编辑权限')


@bot.command(lexer=KeyWord(keyword='.编辑权限列表'))
async def list_edit_permission(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    users = config['edit_permission']
    names = ''
    for i in users:
        user = await get_user(str(i))
        names += f'{user.username}#{user.identify_num}, '
    names = names[:-2]
    await msg.reply(f'编辑权限用户: {names}')


@bot.command(lexer=KeyWord(keyword='.编辑权限删除'))
async def del_edit_permission(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    users = msg.extra['mention']
    if len(users) == 0:
        await msg.reply('请at需要删除的用户')
        return
    if len(users) != 1:
        await msg.reply('删除用户权限一次只能at一位用户')
        return
    config = dict(configs.find_one())
    user = users[0]
    if user not in config['edit_permission']:
        await msg.reply('该用户没有编辑权限')
        return
    config['edit_permission'].remove(user)
    configs.update_one({'guild': msg.ctx.guild.id}, {'$set': config})
    user = await get_user(user)
    user_name = f'{user.username}#{user.identify_num}'
    await msg.reply(f'已删除用户 {user_name} 编辑权限')


@bot.command(lexer=KeyWord(keyword='.绑定频道权限添加'))
async def add_bind_other_permission(msg: Message):
    guild_id = msg.ctx.guild.id
    if not (await check_bind_other_permission(guild_id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    if guild_id == config['guild']:
        await msg.reply('本服务器请设置编辑权限')
        return
    users = msg.extra['mention']
    if len(users) == 0:
        await msg.reply('请at需要添加的用户')
        return
    if guild_id not in config['bind_channel_permission']:
        config['bind_channel_permission'][guild_id] = []
    for i in users:
        user_id = str(i)
        if user_id in config['bind_channel_permission'][guild_id]:
            continue
        else:
            config['bind_channel_permission'][guild_id].append(user_id)
    configs.update_one({'guild': config['guild']}, {'$set': config})
    names = ''
    for i in users:
        user = await get_user(str(i))
        names += f'{user.username}#{user.identify_num}, '
    names = names[:-2]
    await msg.reply(f'已添加用户 {names} 绑定频道权限')


@bot.command(lexer=KeyWord(keyword='.绑定频道权限列表'))
async def list_bind_other_permission(msg: Message):
    guild_id = msg.ctx.guild.id
    if not (await check_bind_other_permission(guild_id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    if guild_id == config['guild']:
        await msg.reply('本服务器请查看编辑权限')
        return
    if guild_id not in config['bind_channel_permission']:
        await msg.reply(f'绑定频道权限用户为空')
        return
    if len(config['bind_channel_permission'][guild_id]) == 0:
        await msg.reply(f'绑定频道权限用户为空')
        return
    names = ''
    for i in config['bind_channel_permission'][guild_id]:
        user = await get_user(str(i))
        names += f'{user.username}#{user.identify_num}, '
    names = names[:-2]
    await msg.reply(f'绑定频道权限用户: {names}')


@bot.command(lexer=KeyWord(keyword='.绑定频道权限删除'))
async def del_bind_other_permission(msg: Message):
    guild_id = msg.ctx.guild.id
    if not (await check_bind_other_permission(guild_id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    if guild_id == config['guild']:
        await msg.reply('本服务器请设置编辑权限')
        return
    users = msg.extra['mention']
    if len(users) == 0:
        await msg.reply('请at需要删除的用户')
        return
    if guild_id not in config['bind_channel_permission']:
        await msg.reply(f'绑定频道权限用户为空')
        return
    user = users[0]
    if user not in config['bind_channel_permission'][guild_id]:
        await msg.reply('该用户没有绑定频道权限')
        return
    config['bind_channel_permission'][guild_id].remove(user)
    configs.update_one({'guild': config['guild']}, {'$set': config})
    user = await get_user(user)
    user_name = f'{user.username}#{user.identify_num}'
    await msg.reply(f'已删除用户 {user_name} 绑定频道权限')


@bot.command(lexer=KeyWord(keyword='.帮助', start_with=False))
async def get_help(msg: Message):
    bot_id = (await bot.fetch_me()).id
    if bot_id in msg.extra['mention']:
        await msg.reply('文档: \nGitHub: [https://hank9999.github.io/MatchesBot/](https://hank9999.github.io/MatchesBot/)\nGitee: [https://hank9999.gitee.io/MatchesBot/](https://hank9999.gitee.io/MatchesBot/)')


@bot.command(lexer=KeyWord(keyword='.批量删除频道'))
async def del_channels(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    channel_ids = msg.content.replace('.批量删除频道', '').replace('(chn)', '').replace('\\(chn\\)', '').strip().split(' ')
    if len(channel_ids) == 0:
        await msg.reply('频道列表为空')
        return
    for i in channel_ids:
        try:
            await msg.gate.request('POST', 'channel/delete', data={'channel_id': i.strip()})
        except HTTPRequester.APIRequestFailed:
            pass
    await msg.reply('频道删除成功')


@bot.command(lexer=KeyWord(keyword='.设置主服务器'))
async def set_main_guild(msg: Message):
    guild_id = msg.ctx.guild.id
    if not (await check_edit_permission(guild_id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    config = dict(configs.find_one())
    config_bak = copy.deepcopy(config)
    config['guild'] = guild_id
    configs.update_one({'guild': config_bak['guild']}, {'$set': config})
    await msg.reply('已设置主服务器')


@bot.command(lexer=KeyWord(keyword='.赛事卡片更新', start_with=False))
async def update_match_card(msg: Message):
    if not (await check_edit_permission(msg.ctx.guild.id, msg.author_id)):
        await msg.reply('您没有权限进行此操作')
        return
    arg = re.sub(r'(?:\(met\)(?:.*)\(met\))?(?:.*)\.赛事卡片更新', '', msg.content, count=0).strip()
    if 'quote' in msg.extra:
        msg_id = msg.extra['quote']['rong_id']
        result = msg_ids.find_one({'_id': msg_id})
        if result is None:
            await msg.reply('没有找到消息对应卡片ID')
            return
        card_id = result['card_id']
        card = cards.find_one({'_id': card_id})
        if card is None:
            await msg.reply('没有找到该卡片')
            return
        msg_id = msg.extra['quote']['rong_id']
        card, _ = await generate_match_card_from_card_id(card_id)
        await msg.gate.request('POST', 'message/update', data={'msg_id': msg_id, 'content': json.dumps(CardMessage(card))})
    else:
        await msg.reply('没有回复赛事卡片')


if __name__ == '__main__':
    bot.run()
