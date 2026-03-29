import asyncio
import json
import websockets
import requests
import time
import hashlib
import hmac
import random
from hashlib import sha256
import struct
import zlib
import edge_tts
import configparser
import os
import sys
import tempfile
from datetime import datetime
from playsound import playsound

TEMP_MP3_FILES = set()

latest_danmaku = ""

def get_formatted_time():
    now = datetime.now()
    return f"[{now.strftime('%Y-%m-%d')}][{now.strftime('%H:%M:%S')}]"

def get_root_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def generate_default_config(auth_code=""):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg["CORE_CONFIG"] = {"auth_code": auth_code, "tts_rate": "+0%", "tts_volume": "+0%", "tts_voice": "zh-CN-XiaoyiNeural"}
    cfg["AI_CONFIG"] = {"ai_enable": "1", "ai_api_base": "这里填ai的接入接口链接", "ai_api_key": "这里填入api key", "ai_model": "这里填ai的模型", "ai_temperature": "0.7", "ai_system_prompt": "你是一个直播间助手，需要帮助主播和观众互动，你喜欢二次元，是个白丝猫娘，说话的时候略微有些胆小，且不擅长一次性说很多话。"}
    cfg["FUNCTION_SWITCH"] = {"welcome_enable": "1", "dm_enable": "1", "like_broadcast_enable": "1", "gift_thank_enable": "1", "guard_enable": "1", "super_chat_enable": "1"}
    cfg["CUSTOM_MSG"] = {"welcome_msg": "欢迎name进入直播间！", "dm_msg": "name说：msg", "like_thank_msg": "感谢name点了count个赞！", "gift_thank_msg": "感谢name赠送gift_num个gift_name！", "guard_msg": "感谢name开通guard_month个月的guard_name！", "super_chat_msg": "感谢name发送的SuperChat，...，message"}
    config_path = os.path.join(get_root_path(), "config.ini")
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            cfg.write(f)
    except Exception as e:
        raise FileNotFoundError(f"❌ 配置文件生成失败：{e}")

def get_auth_code():
    auth_code = ""
    for arg in sys.argv[1:]:
        arg = arg.strip()
        if arg.startswith("code=") and len(arg.split("=")) >= 2:
            auth_code = arg.split("=")[1].strip()
            if auth_code:
                break
    if auth_code:
        return auth_code
    if len(sys.argv) >= 2:
        cmd_auth_code = sys.argv[1].strip()
        if cmd_auth_code:
            return cmd_auth_code
    while True:
        auth_code = input("请输入身份码：").strip()
        if auth_code:
            return auth_code

def load_config():
    cfg = configparser.ConfigParser(interpolation=None)
    config_path = os.path.join(get_root_path(), "config.ini")
    if not os.path.exists(config_path):
        auth_code = get_auth_code()
        generate_default_config(auth_code)
    cfg.read(config_path, encoding="utf-8")
    
    def get_int_safe(section, key, fallback=1):
        try:
            return cfg.getint(section, key, fallback=fallback)
        except:
            return fallback
    
    def get_str_safe(section, key, fallback=""):
        try:
            return cfg.get(section, key, fallback=fallback)
        except:
            return fallback
    
    def get_float_safe(section, key, fallback=0.7):
        try:
            return cfg.getfloat(section, key, fallback=fallback)
        except:
            return fallback

    return {
        "auth_code": get_str_safe("CORE_CONFIG", "auth_code", ""),
        "tts_rate": get_str_safe("CORE_CONFIG", "tts_rate", "+0%"),
        "tts_volume": get_str_safe("CORE_CONFIG", "tts_volume", "+0%"),
        "tts_voice": get_str_safe("CORE_CONFIG", "tts_voice", "zh-CN-XiaoyiNeural"),
        "ai_enable": get_int_safe("AI_CONFIG", "ai_enable", 1),
        "ai_api_base": get_str_safe("AI_CONFIG", "ai_api_base", "这里填ai的接入接口链接"),
        "ai_api_key": get_str_safe("AI_CONFIG", "ai_api_key", "这里填入api key"),
        "ai_model": get_str_safe("AI_CONFIG", "ai_model", "这里填ai的模型"),
        "ai_temperature": get_float_safe("AI_CONFIG", "ai_temperature", 0.7),
        "ai_system_prompt": get_str_safe("AI_CONFIG", "ai_system_prompt", "你是一个直播间助手，需要帮助主播和观众互动，你喜欢二次元，是个白丝猫娘，说话的时候略微有些胆小，且不擅长一次性说很多话。"),
        "welcome_enable": get_int_safe("FUNCTION_SWITCH", "welcome_enable", 1),
        "dm_enable": get_int_safe("FUNCTION_SWITCH", "dm_enable", 1),
        "like_broadcast_enable": get_int_safe("FUNCTION_SWITCH", "like_broadcast_enable", 1),
        "gift_thank_enable": get_int_safe("FUNCTION_SWITCH", "gift_thank_enable", 1),
        "guard_enable": get_int_safe("FUNCTION_SWITCH", "guard_enable", 1),
        "super_chat_enable": get_int_safe("FUNCTION_SWITCH", "super_chat_enable", 1),
        "welcome_msg": get_str_safe("CUSTOM_MSG", "welcome_msg", "欢迎name进入直播间！"),
        "dm_msg": get_str_safe("CUSTOM_MSG", "dm_msg", "name说：msg"),
        "like_thank_msg": get_str_safe("CUSTOM_MSG", "like_thank_msg", "感谢name点了count个赞！"),
        "gift_thank_msg": get_str_safe("CUSTOM_MSG", "gift_thank_msg", "感谢name赠送gift_num个gift_name！"),
        "guard_msg": get_str_safe("CUSTOM_MSG", "guard_msg", "感谢name开通guard_month个月的guard_name！"),
        "super_chat_msg": get_str_safe("CUSTOM_MSG", "super_chat_msg", "感谢name发送的SuperChat，...，message")
    }

def clean_text(raw_text):
    if not raw_text:
        return ""
    return raw_text.strip()

def replace_cn_punc_to_en(text):
    if not text:
        return text
    dic = {
        '，': ',',
        '。': '.',
        '！': '!',
        '？': '?',
        '；': ';',
        '：': ':',
        '“': '"',
        '”': '"',
        '‘': "'",
        '’': "'",
        '（': '(',
        '）': ')',
        '【': '[',
        '】': ']',
        '《': '<',
        '》': '>',
        '—': '-',
        '～': '~',
        '…': '...',
        '、': ','
    }
    for cn, en in dic.items():
        text = text.replace(cn, en)
    return text

CONFIG = load_config()

BILI_FIXED_CONFIG = {
    "app_id": ,
    "access_key": "",
    "secret_key": "",
    "host": "https://live-open.biliapi.com"
}

FIXED_SETTING = {
    "msg_interval": 1,
    "guard_name_map": {1: "总督", 2: "提督", 3: "舰长"},
    "log_file_name": "bili_live_tts.log"
}

class Proto:
    def __init__(self):
        self.packetLen = 0
        self.headerLen = 16
        self.ver = 0
        self.op = 0
        self.seq = 0
        self.body = ''
        self.maxBody = 2048

    def pack(self):
        self.packetLen = len(self.body) + self.headerLen
        buf = struct.pack('>i', self.packetLen)
        buf += struct.pack('>h', self.headerLen)
        buf += struct.pack('>h', self.ver)
        buf += struct.pack('>i', self.op)
        buf += struct.pack('>i', self.seq)
        buf += self.body.encode()
        return buf

    def unpack(self, buf):
        if len(buf) < self.headerLen:
            return False
        self.packetLen = struct.unpack('>i', buf[0:4])[0]
        self.headerLen = struct.unpack('>h', buf[4:6])[0]
        self.ver = struct.unpack('>h', buf[6:8])[0]
        self.op = struct.unpack('>i', buf[8:12])[0]
        self.seq = struct.unpack('>i', buf[12:16])[0]
        if self.packetLen < 0 or self.packetLen > self.maxBody:
            return False
        body_len = self.packetLen - self.headerLen
        self.body = buf[16:self.packetLen] if body_len > 0 else b''
        return True

class BiliLiveTTS:
    def __init__(self):
        self.idCode = CONFIG["auth_code"]
        self.tts_voice = CONFIG["tts_voice"]
        self.tts_rate = CONFIG["tts_rate"]
        self.tts_volume = CONFIG["tts_volume"]
        self.ai_enable = CONFIG["ai_enable"]
        self.ai_api_base = CONFIG["ai_api_base"]
        self.ai_api_key = CONFIG["ai_api_key"]
        self.ai_model = CONFIG["ai_model"]
        self.ai_temperature = CONFIG["ai_temperature"]
        self.ai_system_prompt = CONFIG["ai_system_prompt"]
        self.ai_messages = []
        self.welcome_enable = CONFIG["welcome_enable"]
        self.dm_enable = CONFIG["dm_enable"]
        self.like_broadcast_enable = CONFIG["like_broadcast_enable"]
        self.gift_thank_enable = CONFIG["gift_thank_enable"]
        self.guard_enable = CONFIG["guard_enable"]
        self.super_chat_enable = CONFIG["super_chat_enable"]
        self.welcome_msg = CONFIG["welcome_msg"]
        self.dm_msg = CONFIG["dm_msg"]
        self.like_thank_msg = CONFIG["like_thank_msg"]
        self.gift_thank_msg = CONFIG["gift_thank_msg"]
        self.guard_msg = CONFIG["guard_msg"]
        self.super_chat_msg = CONFIG["super_chat_msg"]
        self.appId = BILI_FIXED_CONFIG["app_id"]
        self.key = BILI_FIXED_CONFIG["access_key"]
        self.secret = BILI_FIXED_CONFIG["secret_key"]
        self.host = BILI_FIXED_CONFIG["host"]
        self.gameId = ''
        self.msg_interval = FIXED_SETTING["msg_interval"]
        self.guard_name_map = FIXED_SETTING["guard_name_map"]
        self.log_file_name = FIXED_SETTING["log_file_name"]
        self.last_msg = ""
        self.last_msg_time = 0
        self.init_log_file()
        self.msg_queue = asyncio.Queue(maxsize=1)
        self.processed_ai_cmd = set()

    def init_log_file(self):
        try:
            log_path = os.path.join(get_root_path(), self.log_file_name)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50} 程序运行日志 {get_formatted_time()} {'='*50}\n")
        except Exception as e:
            print(f"❌ 日志初始化失败：{e}")

    def record_log(self, content, print_to_terminal=True):
        time_stamp = get_formatted_time()
        log_content = f"{time_stamp} {content}"
        try:
            log_path = os.path.join(get_root_path(), self.log_file_name)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_content + "\n")
        except Exception as e:
            if print_to_terminal:
                print(f"❌ 日志写入失败：{e}")
        if print_to_terminal:
            print(content)

    def sign(self, params):
        md5 = hashlib.md5()
        md5.update(params.encode())
        ts = time.time()
        nonce = random.randint(1, 100000) + ts
        md5data = md5.hexdigest()
        headerMap = {
            "x-bili-timestamp": str(int(ts)),
            "x-bili-signature-method": "HMAC-SHA256",
            "x-bili-signature-nonce": str(nonce),
            "x-bili-accesskeyid": self.key,
            "x-bili-signature-version": "1.0",
            "x-bili-content-md5": md5data,
        }
        headerList = sorted(headerMap)
        headerStr = '\n'.join([f"{key}:{headerMap[key]}" for key in headerList])
        signature = hmac.new(self.secret.encode(), headerStr.encode(), sha256).hexdigest()
        headerMap["Authorization"] = signature
        headerMap["Content-Type"] = "application/json"
        headerMap["Accept"] = "application/json"
        return headerMap

    def getWebsocketInfo(self):
        if not self.idCode.strip():
            self.record_log("❌ 请在config.ini中填写auth_code")
            raise Exception("auth_code为空")
        postUrl = f"{self.host}/v2/app/start"
        params = json.dumps({"code": self.idCode, "app_id": self.appId})
        headerMap = self.sign(params)
        try:
            r = requests.post(postUrl, headers=headerMap, data=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            if data.get("code") != 0:
                raise Exception(f"启动失败：{data.get('message')}")
            self.gameId = str(data['data']['game_info']['game_id'])
            return data['data']['websocket_info']['wss_link'][0], data['data']['websocket_info']['auth_body']
        except Exception as e:
            self.record_log(f"❌ 初始化失败：{e}")
            raise

    def init_ai_persona(self):
        if not self.ai_enable or not self.ai_system_prompt.strip():
            return
        self.ai_messages = [{"role": "system", "content": self.ai_system_prompt}]
        self.record_log("🤖 AI人设已初始化：" + self.ai_system_prompt)

    def call_ai_api(self, question):
        if not self.ai_enable:
            self.record_log("❌ AI功能已关闭，无法进行互动")
            return None
        if self.ai_api_key == "这里填入api key" or not self.ai_api_key.strip():
            self.record_log("❌ 请在config.ini中配置有效的AI API Key")
            return None
        self.ai_messages.append({"role": "user", "content": question})
        headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
        payload = {"model": self.ai_model, "messages": self.ai_messages, "temperature": self.ai_temperature}
        try:
            response = requests.post(url=self.ai_api_base, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            ai_reply = result["choices"][0]["message"]["content"].strip()
            self.ai_messages.append({"role": "assistant", "content": ai_reply})
            return ai_reply
        except Exception as e:
            if self.ai_messages and self.ai_messages[-1]["role"] == "user":
                self.ai_messages.pop()
            self.record_log(f"❌ AI调用失败：{e}")
            return None

    async def speak_msg(self, read_text):
        if not read_text.strip() or (read_text == self.last_msg and time.time() - self.last_msg_time < self.msg_interval):
            return
        self.last_msg = read_text
        self.last_msg_time = time.time()
        cleaned_text = clean_text(read_text)
        if not cleaned_text.strip():
            self.record_log("⚠️ 消息为空，跳过播报")
            return
        tts_text = replace_cn_punc_to_en(cleaned_text)
        temp_mp3 = None
        max_retries = 2
        retry_count = 0
        success = False
        while retry_count <= max_retries and not success:
            try:
                communicate = edge_tts.Communicate(text=tts_text, voice=self.tts_voice, rate=self.tts_rate, volume=self.tts_volume)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                    temp_mp3 = temp_file.name
                    TEMP_MP3_FILES.add(temp_mp3)
                await communicate.save(temp_mp3)
                if os.path.exists(temp_mp3):
                    await asyncio.to_thread(playsound, temp_mp3)
                success = True
            except Exception as e:
                retry_count += 1
                if retry_count <= max_retries:
                    self.record_log(f"⚠️ 朗读失败（第{retry_count}次重试）：{e}")
                    await asyncio.sleep(0.5)
                else:
                    self.record_log(f"❌ 朗读失败：{e}")
            finally:
                if temp_mp3 and os.path.exists(temp_mp3):
                    try:
                        os.remove(temp_mp3)
                        TEMP_MP3_FILES.discard(temp_mp3)
                    except Exception as e:
                        self.record_log(f"⚠️ 临时文件清理失败：{e}", print_to_terminal=False)

    async def play_queue_loop(self):
        while True:
            try:
                read_text = await asyncio.wait_for(self.msg_queue.get(), timeout=1)
                await self.speak_msg(read_text)
                self.msg_queue.task_done()
            except asyncio.TimeoutError:
                continue

    def parse_target_msg(self, body):
        global latest_danmaku
        try:
            body_str = body.decode('utf-8')
            msg_data = json.loads(body_str)
            cmd = msg_data.get("cmd")
            read_text = None
            print_text = None

            if cmd == "LIVE_OPEN_PLATFORM_DM" and self.dm_enable == 1:
                data = msg_data['data']
                uname = clean_text(data.get('uname', '未知用户'))
                msg_content = clean_text(data.get('msg', '').strip())
                latest_danmaku = msg_content
                print(f"💬 [弹幕] {uname}：{msg_content}")
                if not msg_content.startswith("\\"):
                    temp = self.dm_msg
                    temp = temp.replace("msg", msg_content)
                    temp = temp.replace("name", uname)
                    read_text = temp
                else:
                    print_text = f"🤖 [AI指令] {uname}：{msg_content}"
                    read_text = None
                    cmd_hash = hash(f"{uname}_{msg_content}_{time.time()}")
                    if cmd_hash not in self.processed_ai_cmd:
                        self.processed_ai_cmd.add(cmd_hash)
                        asyncio.create_task(self.handle_ai_command(uname, msg_content))
                        if len(self.processed_ai_cmd) > 100:
                            self.processed_ai_cmd.clear()

            elif cmd == "LIVE_OPEN_PLATFORM_SEND_GIFT" and self.gift_thank_enable == 1:
                data = msg_data['data']
                uname = clean_text(data.get('uname', '未知用户'))
                gift_name = clean_text(data.get('gift_name', '未知礼物'))
                gift_num = data.get('gift_num', 1)
                print_text = f"🎁 [礼物] {uname} 赠送 {gift_num} 个 {gift_name}"
                temp = self.gift_thank_msg
                temp = temp.replace("gift_name", gift_name)
                temp = temp.replace("gift_num", str(gift_num))
                temp = temp.replace("name", uname)
                read_text = temp

            elif cmd == "LIVE_OPEN_PLATFORM_SUPER_CHAT" and self.super_chat_enable == 1:
                data = msg_data['data']
                uname = clean_text(data.get('uname', '未知用户'))
                message = clean_text(data.get('message', ''))
                rmb = data.get('rmb', 0)
                print_text = f"💎 [SuperChat] {uname}（{rmb}元）：{message}"
                temp = self.super_chat_msg
                temp = temp.replace("message", message)
                temp = temp.replace("rmb", str(rmb))
                temp = temp.replace("name", uname)
                read_text = temp

            elif cmd == "LIVE_OPEN_PLATFORM_GUARD" and self.guard_enable == 1:
                data = msg_data['data']
                uname = clean_text(data['user_info'].get('uname', '未知用户'))
                guard_level = data.get('guard_level', 3)
                guard_num = data.get('guard_num', 1)
                guard_unit = clean_text(data.get('guard_unit', '月').strip())
                guard_name = self.guard_name_map.get(guard_level, "舰长")
                guard_month = guard_num if "月" in guard_unit else 1
                print_text = f"🏆 [大航海] {uname} 开通 {guard_month} 个月 {guard_name}"
                temp = self.guard_msg
                temp = temp.replace("guard_name", guard_name)
                temp = temp.replace("guard_month", str(guard_month))
                temp = temp.replace("name", uname)
                read_text = temp

            elif cmd == "LIVE_OPEN_PLATFORM_LIKE" and self.like_broadcast_enable == 1:
                data = msg_data['data']
                uname = clean_text(data.get('uname', '未知用户'))
                like_count = data.get('like_count', 1)
                print_text = f"❤️ [点赞] {uname} 点赞 {like_count} 次"
                temp = self.like_thank_msg
                temp = temp.replace("count", str(like_count))
                temp = temp.replace("name", uname)
                read_text = temp

            elif cmd == "LIVE_OPEN_PLATFORM_LIVE_ROOM_ENTER" and self.welcome_enable == 1:
                data = msg_data['data']
                uname = clean_text(data.get('uname', '未知用户'))
                print_text = f"👋 [进房] 欢迎 {uname} 进入直播间"
                temp = self.welcome_msg
                temp = temp.replace("name", uname)
                read_text = temp

            elif cmd == "LIVE_OPEN_PLATFORM_LIVE_START":
                data = msg_data.get('data', {})
                area_name = clean_text(data.get('area_name', '未知分区'))
                title = clean_text(data.get('title', '无标题'))
                print_text = f"📢 [开播] 开播啦！当前分区：{area_name}，标题：{title}"
                read_text = f"开播啦！当前分区：{area_name}，标题：{title}"

            elif cmd == "LIVE_OPEN_PLATFORM_LIVE_END":
                print_text = f"🔚 [下播] 下播啦！记得关闭程序哦~"
                read_text = "下播啦！记得关闭程序哦~"

            if print_text and cmd != "LIVE_OPEN_PLATFORM_DM":
                self.record_log(print_text)
            return read_text

        except UnicodeDecodeError:
            self.record_log("❌ 消息体非UTF-8编码，无法解析")
            return None
        except Exception as e:
            self.record_log(f"❌ 消息解析失败：{e}")
            return None

    async def handle_ai_command(self, uname, ai_command):
        global latest_danmaku
        try:
            ai_question = clean_text(ai_command[1:].strip())
            if not ai_question:
                self.record_log("❌ AI指令为空")
                latest_danmaku = ""
                return
            self.record_log(f"🤖 处理AI指令：{ai_question}")
            ai_reply = self.call_ai_api(ai_question)
            if ai_reply:
                cleaned_ai_reply = clean_text(ai_reply)
                tts_ai_reply = replace_cn_punc_to_en(cleaned_ai_reply)
                self.record_log(f"🤖 [AI回复]：{cleaned_ai_reply}")
                ai_communicate = edge_tts.Communicate(text=tts_ai_reply, voice=self.tts_voice, rate=self.tts_rate, volume=self.tts_volume)
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as ai_temp_file:
                    ai_temp_mp3 = ai_temp_file.name
                    TEMP_MP3_FILES.add(ai_temp_mp3)
                await ai_communicate.save(ai_temp_mp3)
                if os.path.exists(ai_temp_mp3):
                    await asyncio.to_thread(playsound, ai_temp_mp3)
                try:
                    os.remove(ai_temp_mp3)
                    TEMP_MP3_FILES.discard(ai_temp_mp3)
                except:
                    pass
            else:
                self.record_log("❌ AI获取回复失败")
            latest_danmaku = ""
        except Exception as e:
            self.record_log(f"❌ AI处理异常：{e}")
            latest_danmaku = ""

    async def auth(self, websocket, auth_body):
        req = Proto()
        req.body = auth_body
        req.op = 7
        await websocket.send(req.pack())
        buf = await websocket.recv()
        resp = Proto()
        if not resp.unpack(buf):
            raise Exception("鉴权失败")
        resp_body = json.loads(resp.body)
        if resp_body["code"] != 0:
            raise Exception(f"鉴权失败：{resp_body.get('message')}")
        self.record_log("✨ 弹幕连接成功！（按 Ctrl+C 可安全关闭程序）")
        self.init_ai_persona()

    async def heartBeat(self, websocket):
        while True:
            await asyncio.sleep(20)
            req = Proto()
            req.op = 2
            await websocket.send(req.pack())

    async def appheartBeat(self):
        while True:
            await asyncio.sleep(20)
            postUrl = f"{self.host}/v2/app/heartbeat"
            params = json.dumps({"game_id": self.gameId})
            headerMap = self.sign(params)
            try:
                requests.post(postUrl, headers=headerMap, data=params, timeout=10)
            except:
                pass

    async def recvLoop(self, websocket):
        self.last_msg_time = 0
        while True:
            recvBuf = await websocket.recv()
            resp = Proto()
            if not resp.unpack(recvBuf):
                continue
            if resp.op == 5:
                try:
                    body = zlib.decompress(resp.body) if resp.ver == 3 else resp.body
                    read_text = self.parse_target_msg(body)
                    if read_text:
                        while not self.msg_queue.empty():
                            self.msg_queue.get_nowait()
                        self.msg_queue.put_nowait(read_text)
                except Exception as e:
                    self.record_log(f"❌ 消息处理失败：{e}")

    async def connect(self):
        addr, authBody = self.getWebsocketInfo()
        websocket = await websockets.connect(addr, open_timeout=30.0)
        await asyncio.sleep(0.5)
        await self.auth(websocket, authBody)
        return websocket

    def close_app(self):
        try:
            for mp3_file in TEMP_MP3_FILES:
                if os.path.exists(mp3_file):
                    try:
                        os.remove(mp3_file)
                    except Exception as e:
                        self.record_log(f"⚠️ 残留临时音频文件清理失败：{mp3_file} - {e}", print_to_terminal=False)
            TEMP_MP3_FILES.clear()
            temp_audio = os.path.join(get_root_path(), "temp_bili_tts.mp3")
            if os.path.exists(temp_audio):
                os.remove(temp_audio)
            postUrl = f"{self.host}/v2/app/end"
            params = json.dumps({"game_id": self.gameId, "app_id": self.appId})
            headerMap = self.sign(params)
            requests.post(postUrl, headers=headerMap, data=params, timeout=10)
            self.record_log("✅ 已正常关闭直播互动应用")
        except Exception as e:
            self.record_log(f"⚠️ 清理资源时出现小问题：{e}")

    async def run(self):
        websocket = None
        try:
            websocket = await self.connect()
            asyncio.create_task(self.play_queue_loop())
            await asyncio.gather(self.recvLoop(websocket), self.heartBeat(websocket), self.appheartBeat())
        except Exception as e:
            self.record_log(f"❌ 程序异常：{e}")
        finally:
            if websocket:
                await websocket.close()
            self.close_app()

def countdown_auto_close(seconds=5):
    print(f"\n✅ 程序已关闭，窗口将在 {seconds} 秒后自动关闭...")
    for i in range(seconds, 0, -1):
        print(f"\r剩余时间：{i} 秒", end="", flush=True)
        time.sleep(1)
    sys.exit(0)

if __name__ == '__main__':
    try:
        client = BiliLiveTTS()
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print("\n📢 已捕获 Ctrl+C 中断，正在清理资源...")
        client.close_app()
    except Exception as e:
        print(f"\n❌ 程序运行异常：{str(e)}")
    finally:
        countdown_auto_close(5)
