"""Supabase(PostgreSQL) 연결 모듈.

백엔드만 service_role 키로 접근한다. 이 키는 RLS를 우회하는 관리자 키이므로
절대 프론트엔드나 저장소(git)에 노출하면 안 된다.
"""
import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# 앱 전체가 공유하는 단일 클라이언트
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
