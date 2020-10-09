
# built-in module
import sys
import pdb
import os
import pandas as pd
import time
from datetime import datetime


# UI(PyQt5) module
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QAxContainer import *
from PyQt5 import uic
from PyQt5 import QtGui

from slacker import Slacker

from kiwoom.kw import Kiwoom
from kiwoom import constant
from config import config_manager
from util.tt_logger import TTlog

from database.db_manager import DBM
from pymongo import MongoClient
import pymongo
import random
from collections import defaultdict

# load main UI object
ui = uic.loadUiType(config_manager.MAIN_UI_PATH)[0]


# main class
class TopTrader(QMainWindow, ui):
    def __init__(self):
        super().__init__()
        self.tt_logger = TTlog().logger
        self.mongo = MongoClient()
        self.tt_db = self.mongo.TopTrader
        self.slack = Slacker(config_manager.SLACK_TOKEN)
        self.kw = Kiwoom()
        self.login()
        # self.update_stock_info()
        self.load_stock_info()
        self.set_account()
        self.auto_trading()
        #print("TopTrader 자동매매 시작합니다...")
        self.timer = None
        self.start_timer()

    def login(self):
        # Login
        err_code = self.kw.login()
        if err_code != 0:
            self.tt_logger.error("Login Fail")
            exit(-1)
        self.tt_logger.info("Login success")

    def load_stock_info(self):
        self.stock_dict = {}
        doc = self.tt_db.stock_information.find({})
        for d in doc:
            code = d["code"]
            self.stock_dict[code] = d
        print("loading stock_information completed.")

    def update_stock_info(self):
        # kospi
        kospi = []
        code_list = self.kw.get_code_list_by_market("0")
        for code in code_list:
            stock_name = self.kw.get_master_stock_name(code)
            kospi.append({"code": code, "stock_name": stock_name, "market": "kospi"})
        self.tt_db.stock_information.insert(kospi)

        # kosdaq
        kosdaq = []
        code_list = self.kw.get_code_list_by_market("10")
        for code in code_list:
            stock_name = self.kw.get_master_stock_name(code)
            kosdaq.append({"code": code, "stock_name": stock_name, "market": "kosdaq"})
        self.tt_db.stock_information.insert(kosdaq)

    def set_account(self):
        self.acc_no = self.kw.get_login_info("ACCNO")
        #self.acc_no = self.acc_no.strip(";")  # 계좌 1개를 가정함.
        acc_nos = self.acc_no.split(";")  # 계좌 1개를 가정함.
        self.acc_no = acc_nos[0]
        self.tt_logger.info("계좌번호:{}".format(self.acc_no))
        self.stock_account = self.account_stat(self.acc_no)
        self.tt_logger.info("잔고 : {}".format(self.stock_account["계좌정보"]["예수금"]))

        # kiwoom default account setting
        self.kw.set_account(self.acc_no)
        print("현재 계좌 현황입니다...")

        if not bool(self.stock_account):
            self.tt_logger.error("계좌정보를 제대로 받아오지 못했습니다.")
            return

        self.my_stocks = {}
        for data in self.stock_account["종목정보"]:
            code, stock_name, quantity = data["종목코드"][1:], data["종목명"], int(data["보유수량"])
            self.tt_logger.info("* 종목: {}, 손익율: {}%, 보유수량: {}, 평가금액: {}원".format(
                data["종목명"], ("%.2f" % data["손익율"]), int(data["보유수량"]), format(int(data["평가금액"]), ',')
            ))
            self.my_stocks[code] = quantity

    def start_timer(self):
        if self.timer:
            self.timer.stop()
            self.timer.deleteLater()
        self.timer = QTimer()
        self.timer.timeout.connect(self.sell)
        # self.timer.setSingleShot(True)
        self.timer.start(5000) # 5 sec interval

    def sell(self):
        print("[Timer Interrupt] 5 second")
        self.stock_account = self.account_stat(self.acc_no)
        curr_time = datetime.today()
        print("=" * 50)
        print("현재 계좌 현황입니다...")

        if not bool(self.stock_account):
            self.tt_logger.error("계좌정보를 제대로 받아오지 못했습니다.")
            return

        for data in self.stock_account["종목정보"]:
            code, stock_name, quantity = data["종목코드"][1:], data["종목명"], int(data["보유수량"])
            print("* 종목: {}, 손익율: {}%, 보유수량: {}, 평가금액: {}원".format(
                data["종목명"], ("%.2f" % data["손익율"]), int(data["보유수량"]), format(int(data["평가금액"]), ',')
            ))

            if data["손익율"] > 3.0 or data["손익율"] < -2.0:
                if data["손익율"] > 0:
                    print("시장가로 물량 전부 익절합니다. ^^    [{}:{}, {}주]".format(stock_name, code, quantity))
                else:
                    print("시장가로 물량 전부 손절합니다. ㅜㅜ. [{}:{}, {}주]".format(stock_name, code, quantity))

                # self.kw.reg_callback("OnReceiveChejanData", ("시장가매도", "5001"), self.account_stat)

                self.kw.시장가_신규매도(code, quantity)
                # self.kw.send_order("시장가매도", "5001", self.acc_no, 2, code, quantity, 0, "03", "")
                '''
                self.tt_db.trading_history.insert({
                    'date': curr_time,
                    'code': code,
                    'stock_name': self.stock_dict[code]["stock_name"],
                    'market': self.stock_dict[code]["market"],
                    'event': '',
                    'condi_name': '',
                    'trade': 'sell',
                    'profit': data["손익율"],
                    'quantity': quantity,
                    'hoga_gubun': '시장가',
                    'account_no': self.acc_no
                })
                '''
        return

    def account_stat(self, acc_no):
        self.tt_logger.info("계좌평가현황요청")
        return self.kw.계좌평가현황요청("계좌평가현황요청", acc_no, "", "1", "6001")

    def search_condi(self, event_data):
        self.kw.logger.info("search_condi tag 0: {}".format(event_data["condi_name"]))
        """키움모듈의 OnReceiveRealCondition 이벤트 수신되면 호출되는 callback함수
        이벤트 정보는 event_data 변수로 전달된다.

            ex)
            event_data = {
                "code": code, # "066570"
                "event_type": event_type, # "I"(종목편입), "D"(종목이탈)
                "condi_name": condi_name, # "스켈핑"
                "condi_index": condi_index # "004"
            }
        :param dict event_data:
        :return:
        """
        curr_time = datetime.today()
        '''
        # 실시간 조건검색 이력정보
        self.tt_db.real_condi_search.insert({
            'date': curr_time,
            'code': event_data["code"],
            'stock_name': self.stock_dict[event_data["code"]]["stock_name"],
            'market': self.stock_dict[event_data["code"]]["market"],
            'event': event_data["event_type"],
            'condi_name': event_data["condi_name"]
        })
        '''

        self.kw.logger.info("search_condi tag 1: {}".format(event_data["condi_name"]))
        #if event_data["event_type"] == "I" and event_data["condi_name"] == "돌파시도 포착 v1.00_r1_m1": #event_data["condi_index"] == "002":
        if event_data["event_type"] == "I" and event_data["condi_name"] == "단순돌파": #event_data["condi_index"] == "002":
        #if event_data["event_type"] == "I" and event_data["condi_name"] == "매도": #event_data["condi_index"] == "002":
            #self.tt_logger.info("잔고 : {}".format(self.stock_account["계좌정보"]["예수금"]))
            #self.tt_logger.info("code : {}".format(event_data["code"]))
            #self.tt_logger.info("event_type : {}".format(event_data["event_type"]))
            #self.tt_logger.info("condi_name : {}".format(event_data["condi_name"]))
            #self.tt_logger.info("condi_index : {}".format(event_data["condi_index"]))
            self.kw.logger.info("search_condi tag 2: {}".format(event_data["condi_name"]))
            if self.stock_account["계좌정보"]["예수금"] < 100000:  # 잔고가 10만원 미만이면 매수 안함
                self.kw.logger.info("잔고가 부족합니다. : {}".format(self.stock_account["계좌정보"]["예수금"]))
                return
            self.kw.logger.info("search_condi tag 3: {}".format(event_data["condi_name"]))
            # curr_price = self.kw.get_curr_price(event_data["code"])
            # quantity = int(100000/curr_price)
            quantity = 10
            # self.kw.reg_callback("OnReceiveChejanData", ("조건식매수", "5000"), self.account_stat)
            #stock_name = self.stock_dict[event_data["code"]]["stock_name"]
            self.kw.logger.info("search_condi tag 3.0: {}".format(event_data["condi_name"]))
            #market = self.stock_dict[event_data["code"]]["market"]
            self.kw.logger.info("search_condi tag 3.1: {}".format(event_data["condi_name"]))
            '''
            self.tt_db.trading_history.insert({
                'date': curr_time,
                'code': event_data["code"],
                'stock_name': stock_name,
                'market': market,
                'event': event_data["event_type"],
                'condi_name': event_data["condi_name"],
                'trade': 'buy',
                'quantity': quantity,
                'hoga_gubun': '시장가',
                'account_no': self.acc_no
            })
            '''
            self.kw.logger.info("{}를 {}주 시장가_신규매수합니다.".format(event_data["code"], quantity))
            self.kw.logger.info("search_condi tag 4: {}".format(event_data["condi_name"]))
            self.kw.시장가_신규매수(event_data["code"], quantity)
            if event_data["code"] in self.my_stocks:
                self.my_stocks[event_data["code"]] += quantity
            else:
                self.my_stocks[event_data["code"]] = quantity
            self.kw.logger.info("search_condi tag 5: {}".format(event_data["condi_name"]))
            # self.kw.send_order("조건식매수", "5000", self.acc_no, 1, event_data["code"], quantity, 0, "03", "")
        elif event_data["event_type"] == "I" and event_data["condi_name"] == "매도":
            if event_data["code"] not in self.my_stocks:
                return
            quantity = self.my_stocks[event_data["code"]]
            # self.kw.reg_callback("OnReceiveChejanData", ("조건식매수", "5000"), self.account_stat)
            #stock_name = self.stock_dict[event_data["code"]]["stock_name"]
            #market = self.stock_dict[event_data["code"]]["market"]
            '''
            self.tt_db.trading_history.insert({
                'date': curr_time,
                'code': event_data["code"],
                'stock_name': stock_name,
                'market': market,
                'event': event_data["event_type"],
                'condi_name': event_data["condi_name"],
                'trade': 'sell',
                'quantity': quantity,
                'hoga_gubun': '시장가',
                'account_no': self.acc_no
            })
            '''
            self.kw.logger.info("{}를 {}주 시장가_신규매도합니다.".format(event_data["code"], quantity))
            self.kw.시장가_신규매도(event_data["code"], quantity)

    def auto_trading(self):
        """키움증권 HTS에 등록한 조건검색식에서 검출한 종목을 매수하고
        -2%, +3%에 손절/익절 매도하는 기본적인 자동매매 함수

        :return:
        """
        # callback fn 등록
        self.kw.reg_callback("OnReceiveRealCondition", "", self.search_condi)
        # self.kw.notify_fn["OnReceiveRealCondition"] = self.search_condi

        screen_no = "4000"
        condi_info = self.kw.get_condition_load()
        # {'추천조건식01': '002', '추천조건식02': '000', '급등/상승_추세조건': '001', 'Envelop횡단': '003', '스켈핑': '004'}
        for condi_name, condi_id in condi_info.items():
            # 화면번호, 조건식이름, 조건식ID, 실시간조건검색(1)
            if int(condi_id) == 2:
                self.kw.send_condition(screen_no, condi_name, int(condi_id), 1)
                time.sleep(0.2)

# Print Exception Setting
sys._excepthook = sys.excepthook


def exception_hook(exctype, value, traceback):
    sys._excepthook(exctype, value, traceback)
    sys.exit(1)


sys.excepthook = exception_hook

if __name__ == "__main__":
    app = QApplication(sys.argv)
    tt = TopTrader()
    tt.show()
    sys.exit(app.exec_())
