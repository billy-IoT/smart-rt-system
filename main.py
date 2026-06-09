from __future__ import annotations
import os, re, time, json, uuid, queue, pytz, threading, datetime
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Generic, TypeVar, Protocol
from dataclasses import dataclass, field
import telebot
from telebot import types
from groq import Groq

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ADMIN_ID = str(os.getenv("ADMIN_ID", ""))
CHAT_ID_GRUP = str(os.getenv("CHAT_ID_GRUP", ""))

BOT_NAME = "SATRIA (Sistem Tanggap RT Ih Asique)"
TIMEZONE = "Asia/Jakarta"

MAX_CHAT_HISTORY = 10
MAX_SPAM_MESSAGES = 10
SPAM_WINDOW_SECONDS = 60

class UserRole(str, Enum):
    WARGA = "WARGA"
    ADMIN = "ADMIN"

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class ReportType(str, Enum):
    LAPORAN = "LAPORAN"
    KELUHAN = "KELUHAN"
    DARURAT = "DARURAT"

class SessionState(str, Enum):
    NONE = "NONE"
    WAITING_NAME = "WAITING_NAME"
    WAITING_CATEGORY = "WAITING_CATEGORY"
    WAITING_DESC = "WAITING_DESC"
    WAITING_AMOUNT = "WAITING_AMOUNT"
    WAITING_PHOTO = "WAITING_PHOTO"

class EventType(str, Enum):
    USER_REGISTERED = "USER_REGISTERED"
    REPORT_CREATED = "REPORT_CREATED"
    PAYMENT_SUBMITTED = "PAYMENT_SUBMITTED"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    BROADCAST_CREATED = "BROADCAST_CREATED"

class SATRIAException(Exception): pass
class AIException(SATRIAException): pass
class ServiceException(SATRIAException): pass

class Clock:
    @staticmethod
    def now() -> datetime.datetime:
        return datetime.datetime.now(pytz.timezone(TIMEZONE))

class IdGenerator:
    @staticmethod
    def generate() -> str:
        return str(uuid.uuid4())

class RoleHelper:
    @staticmethod
    def get_role(user_id: str) -> UserRole:
        return UserRole.ADMIN if str(user_id) == str(ADMIN_ID) else UserRole.WARGA

class GreetingHelper:
    @staticmethod
    def greeting() -> str:
        hour = Clock.now().hour
        if 5 <= hour < 12: return "Pagi"
        if 12 <= hour < 15: return "Siang"
        if 15 <= hour < 18: return "Sore"
        return "Malam"

@dataclass(slots=True)
class User:
    id: str
    telegram_id: str
    full_name: str
    username: str
    role: UserRole
    created_at: datetime.datetime

@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str
    created_at: datetime.datetime

@dataclass(slots=True)
class CitizenReport:
    id: str
    user_id: str
    report_type: ReportType
    content: str
    status: ApprovalStatus
    created_at: datetime.datetime

@dataclass(slots=True)
class KasTransaction:
    id: str
    user_id: str
    full_name: str
    category: str
    description: str
    amount: int
    status: ApprovalStatus
    photo_file_id: str
    created_at: datetime.datetime

@dataclass(slots=True)
class BroadcastMessage:
    id: str
    sender_id: str
    message: str
    created_at: datetime.datetime

@dataclass(slots=True)
class ApprovalRequest:
    id: str
    target_id: str
    requester_id: str
    approval_type: str
    created_at: datetime.datetime

@dataclass(slots=True)
class UserSession:
    user_id: str
    state: SessionState
    data: Dict[str, Any] = field(default_factory=dict)
    updated_at: datetime.datetime = field(default_factory=Clock.now)

@dataclass(slots=True)
class RegisterUserDTO:
    telegram_id: str
    full_name: str
    username: str

@dataclass(slots=True)
class CreateReportDTO:
    user_id: str
    report_type: ReportType
    content: str

@dataclass(slots=True)
class CreateKasDTO:
    user_id: str
    full_name: str
    category: str
    description: str
    amount: int
    photo_file_id: str

@dataclass(slots=True)
class BroadcastDTO:
    sender_id: str
    message: str

T = TypeVar("T")
K = TypeVar("K")

class Repository(ABC, Generic[T, K]):
    @abstractmethod
    def save(self, entity: T) -> T: pass
    @abstractmethod
    def find_by_id(self, key: K) -> Optional[T]: pass
    @abstractmethod
    def find_all(self) -> List[T]: pass

class Service(ABC):
    @abstractmethod
    def name(self) -> str: pass

class EventHandler(Protocol):
    def __call__(self, payload: Any) -> None: ...

@dataclass(slots=True)
class ApplicationContext:
    bot_token: str
    groq_api_key: str
    admin_id: str
    group_id: str
    started_at: datetime.datetime
    application_id: str

context = ApplicationContext(BOT_TOKEN, GROQ_API_KEY, ADMIN_ID, CHAT_ID_GRUP, Clock.now(), IdGenerator.generate())
bot = telebot.TeleBot(BOT_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
kas_summary = {"total": 0, "Kebersihan": 0, "Keamanan": 0, "Lain-lain": 0}

class InMemoryRepository(Repository[T, str], Generic[T]):
    def __init__(self) -> None:
        self._storage: Dict[str, T] = {}
        self._lock = threading.RLock()
    def save(self, entity: T) -> T:
        with self._lock:
            entity_id = getattr(entity, "id")
            self._storage[entity_id] = entity
            return entity
    def find_by_id(self, key: str) -> Optional[T]:
        with self._lock: return self._storage.get(key)
    def find_all(self) -> List[T]:
        with self._lock: return list(self._storage.values())

class UserRepository(InMemoryRepository[User]):
    def find_by_telegram_id(self, telegram_id: str) -> Optional[User]:
        with self._lock:
            for user in self._storage.values():
                if user.telegram_id == telegram_id: return user
        return None
    def find_by_username(self, username: str) -> Optional[User]:
        with self._lock:
            for user in self._storage.values():
                if user.username and user.username.lower() == username.lower(): return user
        return None

class ReportRepository(InMemoryRepository[CitizenReport]): pass
class KasRepository(InMemoryRepository[KasTransaction]): pass
class BroadcastRepository(InMemoryRepository[BroadcastMessage]): pass
class ApprovalRepository(InMemoryRepository[ApprovalRequest]): pass

class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, UserSession] = {}
        self._lock = threading.RLock()
    def create(self, user_id: str) -> UserSession:
        with self._lock:
            session = UserSession(user_id=user_id, state=SessionState.NONE)
            self._sessions[user_id] = session
            return session
    def get(self, user_id: str) -> UserSession:
        with self._lock:
            if user_id not in self._sessions: return self.create(user_id)
            return self._sessions[user_id]
    def remove(self, user_id: str) -> None:
        with self._lock: self._sessions.pop(user_id, None)

class ChatHistoryStore:
    def __init__(self) -> None:
        self._storage: Dict[str, List[ChatMessage]] = {}
        self._lock = threading.RLock()
    def add_message(self, user_id: str, role: str, content: str) -> None:
        with self._lock:
            self._storage.setdefault(user_id, [])
            self._storage[user_id].append(ChatMessage(role, content, Clock.now()))
            self._storage[user_id] = self._storage[user_id][-MAX_CHAT_HISTORY:]
    def get_history(self, user_id: str) -> List[ChatMessage]:
        with self._lock: return list(self._storage.get(user_id, []))

class EventBus:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._lock = threading.RLock()
    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        with self._lock:
            self._subscribers.setdefault(event_name, [])
            self._subscribers[event_name].append(handler)
    def publish(self, event_name: str, payload: Any) -> None:
        handlers = []
        with self._lock: handlers = list(self._subscribers.get(event_name, []))
        for handler in handlers:
            try: handler(payload)
            except: pass

@dataclass(slots=True)
class QueueTask:
    task_id: str
    task_name: str
    payload: Any
    callback: Callable[[Any], None]

class QueueManager:
    def __init__(self) -> None:
        self._queue = queue.Queue()
        self._running = False
        self._workers: List[threading.Thread] = []
    def start(self, workers: int = 2) -> None:
        if self._running: return
        self._running = True
        for index in range(workers):
            worker = threading.Thread(target=self._run, daemon=True, name=f"worker-{index}")
            worker.start()
            self._workers.append(worker)
    def submit(self, task: QueueTask) -> None: self._queue.put(task)
    def _run(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=1)
                task.callback(task.payload)
            except: continue

class MetricsCollector:
    def __init__(self) -> None:
        self._metrics: Dict[str, int] = {}
        self._lock = threading.RLock()
    def increment(self, metric: str, value: int = 1) -> None:
        with self._lock: self._metrics[metric] = self._metrics.get(metric, 0) + value

class Container:
    def __init__(self) -> None: self._services: Dict[str, Any] = {}
    def register(self, name: str, service: Any) -> None: self._services[name] = service
    def resolve(self, name: str) -> Any: return self._services.get(name)

users_repository = UserRepository()
reports_repository = ReportRepository()
kas_repository = KasRepository()
approval_repository = ApprovalRepository()
broadcast_repository = BroadcastRepository()
session_manager = SessionManager()
history_store = ChatHistoryStore()
event_bus = EventBus()
queue_manager = QueueManager()
metrics = MetricsCollector()
container = Container()

queue_manager.start(workers=4)
container.register("users_repository", users_repository)
container.register("reports_repository", reports_repository)
container.register("kas_repository", kas_repository)
container.register("approval_repository", approval_repository)
container.register("broadcast_repository", broadcast_repository)
container.register("session_manager", session_manager)
container.register("history_store", history_store)
container.register("event_bus", event_bus)
container.register("queue_manager", queue_manager)
container.register("metrics", metrics)

class UserService(Service):
    def __init__(self, repository: UserRepository) -> None: self._repository = repository
    def name(self) -> str: return "user_service"
    def register_user(self, dto: RegisterUserDTO) -> User:
        existing = self._repository.find_by_telegram_id(dto.telegram_id)
        if existing: return existing
        user = User(IdGenerator.generate(), dto.telegram_id, dto.full_name, dto.username or "", RoleHelper.get_role(dto.telegram_id), Clock.now())
        self._repository.save(user)
        return user

class AIService(Service):
    def __init__(self, history: ChatHistoryStore) -> None: self._history = history
    def name(self) -> str: return "ai_service"
    def ask(self, user: User, prompt: str) -> str:
        history = self._history.get_history(user.telegram_id)
        messages = [{"role": "system", "content": f"Nama Bot: {BOT_NAME}\nUser: {user.full_name}\nRole: {user.role.value}\nSantai dan singkat."}]
        for item in history: messages.append({"role": item.role, "content": item.content})
        messages.append({"role": "user", "content": prompt})
        try:
            response = groq_client.chat.completions.create(model="llama-3.1-8b-instant", messages=messages)
            answer = response.choices[0].message.content
            self._history.add_message(user.telegram_id, "user", prompt)
            self._history.add_message(user.telegram_id, "assistant", answer)
            return answer
        except: return "⚠️ AI Error."

class ReportService(Service):
    def __init__(self, repository: ReportRepository) -> None: self._repository = repository
    def name(self) -> str: return "report_service"
    def create(self, dto: CreateReportDTO) -> CitizenReport:
        report = CitizenReport(IdGenerator.generate(), dto.user_id, dto.report_type, dto.content, ApprovalStatus.PENDING, Clock.now())
        self._repository.save(report)
        return report

class KasService(Service):
    def __init__(self, repository: KasRepository) -> None: self._repository = repository
    def name(self) -> str: return "kas_service"
    def submit(self, dto: CreateKasDTO) -> KasTransaction:
        transaction = KasTransaction(IdGenerator.generate(), dto.user_id, dto.full_name, dto.category, dto.description, dto.amount, ApprovalStatus.PENDING, dto.photo_file_id, Clock.now())
        self._repository.save(transaction)
        approval_repository.save(ApprovalRequest(IdGenerator.generate(), transaction.id, dto.user_id, "KAS", Clock.now()))
        return transaction

class ApprovalService(Service):
    def __init__(self, kas_repo: KasRepository) -> None: self._kas_repo = kas_repo
    def name(self) -> str: return "approval_service"
    def approve(self, transaction_id: str) -> Optional[KasTransaction]:
        trx = self._kas_repo.find_by_id(transaction_id)
        if not trx: return None
        trx.status = ApprovalStatus.APPROVED
        self._kas_repo.save(trx)
        kas_summary["total"] += trx.amount
        kas_summary[trx.category] += trx.amount
        return trx
    def reject(self, transaction_id: str) -> Optional[KasTransaction]:
        trx = self._kas_repo.find_by_id(transaction_id)
        if not trx: return None
        trx.status = ApprovalStatus.REJECTED
        self._kas_repo.save(trx)
        return trx

class BroadcastService(Service):
    def __init__(self, repository: BroadcastRepository) -> None: self._repository = repository
    def name(self) -> str: return "broadcast_service"
    def broadcast(self, dto: BroadcastDTO) -> None:
        message = BroadcastMessage(IdGenerator.generate(), dto.sender_id, dto.message, Clock.now())
        self._repository.save(message)
        for user in users_repository.find_all():
            task = QueueTask(IdGenerator.generate(), "broadcast", (user.telegram_id, dto.message), self._send_worker)
            queue_manager.submit(task)
    def _send_worker(self, payload: Any) -> None:
        user_id, text = payload
        try: bot.send_message(user_id, f"📢 {text}")
        except: pass

class SpamProtectionService(Service):
    def __init__(self) -> None:
        self._storage: Dict[str, List[float]] = {}
        self._lock = threading.RLock()
    def name(self) -> str: return "spam_service"
    def validate(self, user_id: str) -> bool:
        now = time.time()
        with self._lock:
            self._storage.setdefault(user_id, [])
            records = self._storage[user_id]
            records[:] = [x for x in records if now - x < SPAM_WINDOW_SECONDS]
            records.append(now)
            return len(records) <= MAX_SPAM_MESSAGES

user_service = UserService(users_repository)
ai_service = AIService(history_store)
report_service = ReportService(reports_repository)
kas_service = KasService(kas_repository)
approval_service = ApprovalService(kas_repository)
broadcast_service = BroadcastService(broadcast_repository)
spam_service = SpamProtectionService()
notification_service = type('NotificationService', (Service,), {'name': lambda self: 'notification', 'send': lambda self, u, t: bot.send_message(u, t)})()

def is_admin(user_id: str) -> bool: return str(user_id) == str(ADMIN_ID)
def is_bot_target(message) -> bool:
    if message.chat.type == "private": return True
    if message.reply_to_message and message.reply_to_message.from_user.is_bot: return True
    try:
        username = bot.get_me().username
        if message.text and f"@{username}" in message.text: return True
    except: pass
    return False

def register_user_from_message(message) -> User:
    telegram_id = str(message.from_user.id)
    dto = RegisterUserDTO(telegram_id, message.from_user.first_name or "Warga", message.from_user.username or "")
    return user_service.register_user(dto)

def process_iuran_flow(message) -> bool:
    user_id = str(message.from_user.id)
    session = session_manager.get(user_id)
    state = session.state
    if state == SessionState.NONE: return False
    if state == SessionState.WAITING_NAME:
        session.data["full_name"] = message.text
        session.state = SessionState.WAITING_CATEGORY
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Kebersihan", "Keamanan", "Lain-lain")
        bot.send_message(message.chat.id, "Pilih kategori:", reply_markup=markup)
        return True
    if state == SessionState.WAITING_CATEGORY:
        session.data["category"] = message.text
        if message.text == "Lain-lain":
            session.state = SessionState.WAITING_DESC
            bot.reply_to(message, "Masukkan keterangan:")
        else:
            session.data["description"] = "-"
            session.state = SessionState.WAITING_AMOUNT
            bot.reply_to(message, "Masukkan nominal:")
        return True
    if state == SessionState.WAITING_DESC:
        session.data["description"] = message.text
        session.state = SessionState.WAITING_AMOUNT
        bot.reply_to(message, "Masukkan nominal:")
        return True
    if state == SessionState.WAITING_AMOUNT:
        amount = re.sub(r"\D", "", message.text)
        if not amount.isdigit():
            bot.reply_to(message, "Nominal tidak valid.")
            return True
        session.data["amount"] = int(amount)
        session.state = SessionState.WAITING_PHOTO
        bot.reply_to(message, "Kirim foto bukti transfer.")
        return True
    if state == SessionState.WAITING_PHOTO:
        if not message.photo:
            bot.reply_to(message, "Kirim foto.")
            return True
        dto = CreateKasDTO(user_id, session.data["full_name"], session.data["category"], session.data["description"], session.data["amount"], message.photo[-1].file_id)
        transaction = kas_service.submit(dto)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve:{transaction.id}"), types.InlineKeyboardButton("❌ Reject", callback_data=f"reject:{transaction.id}"))
        try: bot.send_photo(ADMIN_ID, dto.photo_file_id, caption=f"💰 Iuran\nNama: {dto.full_name}\nKategori: {dto.category}\nJumlah: Rp{dto.amount:,}", reply_markup=markup)
        except: pass
        session_manager.remove(user_id)
        bot.reply_to(message, "✅ Menunggu approval Pak RT.")
        return True
    return False

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try: action, trx_id = call.data.split(":")
    except: return
    if action == "approve":
        trx = approval_service.approve(trx_id)
        if trx: bot.send_message(trx.user_id, "✅ Iuran disetujui."); bot.answer_callback_query(call.id, "Approved")
    elif action == "reject":
        trx = approval_service.reject(trx_id)
        if trx: bot.send_message(trx.user_id, "❌ Iuran ditolak."); bot.answer_callback_query(call.id, "Rejected")

@bot.message_handler(content_types=["text", "photo"])
def main_handler(message):
    register_user_from_message(message)
    user_id = str(message.from_user.id)
    if not spam_service.validate(user_id): bot.reply_to(message, "⚠️ Terlalu banyak pesan."); return
    if process_iuran_flow(message): return
    text = message.text or message.caption or ""
    if text == "💰 Lapor Iuran": session_manager.get(user_id).state = SessionState.WAITING_NAME; bot.reply_to(message, "Nama Lengkap?"); return
    lower = text.lower()
    if any(key in lower for key in ["lapor", "keluhan", "bermasalah", "parkir"]):
        report = report_service.create(CreateReportDTO(user_id, ReportType.LAPORAN, text))
        bot.reply_to(message, "✅ Laporan diterima.")
        if CHAT_ID_GRUP:
            try: bot.send_message(CHAT_ID_GRUP, f"📢 Laporan Warga\n\n{report.content}")
            except: pass
        usernames = re.findall(r'@(\w+)', text)
        for u in usernames:
            target = users_repository.find_by_username(u)
            if target:
                ai_notif = ai_service.ask(target, f"Buatkan pesan notifikasi sopan kepada {target.full_name} bahwa mereka disebut dalam laporan warga terkait: {text}")
                notification_service.send(target.telegram_id, ai_notif)
        return
    if text.startswith("/bc ") and is_admin(user_id):
        broadcast_service.broadcast(BroadcastDTO(user_id, text.replace("/bc ", "")))
        bot.reply_to(message, "📢 Broadcast dikirim.")
        return
    if not is_bot_target(message): return
    try:
        user = users_repository.find_by_telegram_id(user_id)
        bot.reply_to(message, ai_service.ask(user, text))
    except: bot.reply_to(message, "⚠️ AI Error.")

bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
``` 🗿
