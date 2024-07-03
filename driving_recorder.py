from flask import Flask, render_template, Response, request, jsonify

import cv2
import atexit
import ssl
from bs4 import BeautifulSoup
import requests
import subprocess
import os
import signal
import pymysql
import datetime

from lib_oled96 import ssd1306

from smbus import SMBus
from PIL import ImageFont
import textwrap

font_size = 10
font = ImageFont.load_default()
font = ImageFont.truetype('NanumGothic.ttf', font_size)

i2cbus = SMBus(1)        # 1 = Raspberry Pi but NOT early REV1 board

oled = ssd1306(i2cbus)   # create oled object, nominating the correct I2C bus, default address

url = "https://mobleqr.iptime.org"
app = Flask(__name__)
camera = cv2.VideoCapture(0)
now = datetime.datetime.now()
now_str = now.strftime("%y-%m-%d %H:%M:%S")

value = ""

def shutdown_server():
    pid = os.getpid()
    os.kill(pid, signal.SIGINT)


@app.route("/shutdown", methods=["POST"])
def shutdown():
    shutdown_server()
    return "Server shut down"


def scrape_and_print(url):
    while 1:
        response = requests.get(url)
        html_content = response.text

        soup = BeautifulSoup(html_content, "html.parser")

        # 예를 들어, 모든 <p> 태그의 텍스트를 추출
        texts = soup.find_all(id="outputData").get_text()
        if texts == " ":
            print("텍스트가 없습니다.")
        else:
            for text in texts:
                print(text.get_text())


# OpenCV를 사용하여 카메라 스트림을 생성하는 함수
def gen_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode(".jpg", frame)
            frame = buffer.tobytes()
            yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.route("/")
def index():
    return render_template("index.html")


###########################################################################################
current_time = datetime.datetime.now()
formatted_time = current_time.strftime("%y-%m-%d %H:%M:%S")


# sql 데이터 베이스 접속
conn = pymysql.connect(
    host="127.0.0.1", user="root", password="1234", db="hanbit", charset="utf8"
)
# 데이터 위치 접속(?)
cur = conn.cursor()

# # 테이블 생성
cur.execute("CREATE TABLE IF NOT EXISTS endpj (도착시간 CHAR(30), 주소 CHAR(100));")
cur.execute("DELETE FROM endpj WHERE 1")
# cur.execute("DELETE FROM hanbit1")
conn.commit()

@app.route("/qrvalue", methods=["GET"])
def qr_value():
    global destination
    global value
    global now_str
    
    # sql 데이터 베이스 접속
    conn = pymysql.connect(
        host="127.0.0.1", user="root", password="1234", db="hanbit", charset="utf8"
    )
    # 데이터 위치 접속(?)
    cur = conn.cursor()
    # 데이터 입력
    # cur.execute(
    #     f"INSERT INTO hanbit1 VALUES('{startLocation}', '{formatted_time}', '없음',1)"
    # )

    # cur.execute("INSERT INTO hanbit1 VALUES('경유지', '04-05-17:40', '없음',2)")
    # cur.execute("INSERT INTO hanbit1 VALUES('도착지', '04-05-18:35', '없음',3)")
    value = request.args.get("value")  # 코드에서 fetch로 전송한 데이터 받기
    print("Received QR code data:", value)  # 받은 데이터를 터미널에 출력
    cur.execute(f"INSERT INTO endpj VALUES('{now_str}', '{value}')")
    cur.execute("SELECT * FROM endpj")
    rows = cur.fetchall()
    file_path = r"/home/pi/webapps/end_rp/record/data.txt"
    with open(file_path, "w") as f:
        for row in rows:
            f.write(f"{row}\n")
    
    oled.canvas.rectangle((0, 0, oled.width-1, oled.height-1), outline=1, fill=0)
    if rows:
        # OLED 출력
        oled.canvas.text((30, 5), "*현재 위치*", font=font, fill=1)
        for i in range(len(rows[0])):
            text = rows[len(rows) - 1][i]  # 현재 행의 문자열을 가져옵니다.
            # 텍스트 줄 바꿈 처리
            wrapped_text = textwrap.fill(text, width=int(oled.width / (font_size * 0.75)))
            # 텍스트 그리기
            oled.canvas.text((5, font_size * (i + 1) + 5), wrapped_text, font=font, fill=1)
    else:
        oled.canvas.text((20,25), "데이터 없음", font=font, fill=1)
    oled.display()
  
    # 저장
    conn.commit()
    address = value.split()
    print(address[-1] + "에 도착하였습니다.")
    if address[-1] == destination:
        print("운행을 종료합니다.")
        subprocess.run(
            [
                "sudo",
                "/home/pi/webapps/env/bin/python",
                "/home/pi/webapps/end_rp/car_security.py"
            ]
        )

        shutdown_server()
    return "Received QR code data: " + value  # 응답


# 목적지 입력으로 돌아가기
@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

# /customer 라우트에 대한 핸들러 함수
@app.route("/customer")
def delivery_tracking():
    # sql 데이터 베이스 접속
    conn = pymysql.connect(
        host="127.0.0.1", user="root", password="1234", db="hanbit", charset="utf8"
    )
    # 데이터 위치 접속(?)
    cur = conn.cursor()
    cur.execute("SELECT * FROM endpj")
    rows = cur.fetchall()
    
    # global rows
    # global cur
    # rows = cur.fetchall()
    # index2.html 템플릿에 데이터를 전달하여 렌더링합니다.
    return render_template("index2.html", message=rows)

# /customer 라우트에 대한 핸들러 함수
@app.route("/update")
def update_cell():
    # 데이터베이스에 연결
    conn = pymysql.connect(
        host="127.0.0.1", user="root", password="1234", db="hanbit", charset="utf8"
    )
    # 커서 생성
    cur = conn.cursor()
    # 데이터베이스에서 데이터 가져오기
    cur.execute("SELECT * FROM endpj")
    rows = cur.fetchall()
    # JSON으로 변환
    data = []
    for row in rows:
        data.append(
            {
                "도착시간": row[0],
                "주소": row[1],
            }
        )
    # 연결 및 커서 닫기
    cur.close()
    conn.close()
    # JSON 형식으로 반환
    return jsonify(data)

def release_camera():
    camera.release()


if __name__ == "__main__":
    destination = input("목적지를 입력하세요 : ")
    if destination != "":
        ssl_context1 = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context1.load_cert_chain(
            certfile=r"/home/pi/webapps/end_rp/jsQR/server.crt",
            keyfile=r"/home/pi/webapps/end_rp/jsQR/server.key",
            password="1234",
        )
        atexit.register(release_camera)
        app.run(
            host="0.0.0.0",
            ssl_context=ssl_context1,
            debug=True,
            port=443,
            use_reloader=False,
        )
