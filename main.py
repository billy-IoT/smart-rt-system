from __future__ import annotations
import os, time, uuid, threading, datetime, re, logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Generic, TypeVar, Protocol
from dataclasses import dataclass, field
import telebot
from telebot import types
from groq import Groq

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("SATRIA_ENTERPRISE")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
ADMIN_ID = str(os.getenv("ADMIN_ID", ""))
CHAT_ID_GRUP = str(os.getenv("CHAT_ID_GRUP", ""))

class Configuration:
    def __init__(self):
        self.bot_token = BOT_TOKEN
        self.groq_key = GROQ_API_KEY
        self.admin_id = ADMIN_ID
        self.group_id = CHAT_ID_GRUP
        self.timezone = "Asia/Jakarta"
        self.validate()
    def validate(self):
        if not self.bot_token: raise ValueError("BOT_TOKEN missing")
        if not self.groq_key: raise ValueError("GROQ_API_KEY missing")

class SATRIAException(Exception): pass
class ConfigException(SATRIAException): pass
class RepositoryException(SATRIAException): pass
class ServiceException(SATRIAException): pass
class AIException(SATRIAException): pass

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

@dataclass(slots=True)
class User:
    id: str
    telegram_id: str
    full_name: str
    username: str
    role: UserRole
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
    updated_at: datetime.datetime = field(default_factory=datetime.datetime.now)

T = TypeVar("T")
K = TypeVar("K")

class Repository(ABC, Generic[T, K]):
    @abstractmethod
    def save(self, entity: T) -> T: pass
    @abstractmethod
    def find_by_id(self, key: K) -> Optional[T]: pass
    @abstractmethod
    def find_all(self) -> List[T]: pass
    @abstractmethod
    def delete(self, key: K) -> bool: pass

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
    def delete(self, key: str) -> bool:
        with self._lock: return self._storage.pop(key, None) is not None

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

class Service(ABC):
    @abstractmethod
    def name(self) -> str: pass

class IdGenerator:
    @staticmethod
    def generate() -> str: return str(uuid.uuid4())

class Clock:
    @staticmethod
    def now() -> datetime.datetime: return datetime.datetime.now()

class RoleHelper:
    @staticmethod
    def get_role(user_id: str, admin_id: str) -> UserRole:
        return UserRole.ADMIN if str(user_id) == str(admin_id) else UserRole.WARGA

class Context:
    def __init__(self, cfg: Configuration):
        self.cfg = cfg
        self.app_id = IdGenerator.generate()
        self.started_at = Clock.now()

config = Configuration()
context = Context(config)
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
    def update_state(self, user_id: str, state: SessionState) -> None:
        with self._lock:
            session = self.get(user_id)
            session.state = state
            session.updated_at = Clock.now()

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
    def start(self, workers: int = 4) -> None:
        if self._running: return
        self._running = True
        for i in range(workers):
            t = threading.Thread(target=self._run, daemon=True, name=f"worker-{i}")
            t.start()
            self._workers.append(t)
    def stop(self) -> None: self._running = False
    def submit(self, task: QueueTask) -> None: self._queue.put(task)
    def _run(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=1)
                task.callback(task.payload)
            except queue.Empty: continue
            except: continue

class MetricsCollector:
    def __init__(self) -> None:
        self._metrics: Dict[str, int] = {}
        self._lock = threading.RLock()
    def increment(self, metric: str, value: int = 1) -> None:
        with self._lock: self._metrics[metric] = self._metrics.get(metric, 0) + value
    def get(self, metric: str) -> int:
        with self._lock: return self._metrics.get(metric, 0)

class Container:
    def __init__(self) -> None: self._services: Dict[str, Any] = {}
    def register(self, name: str, service: Any) -> None: self._services[name] = service
    def resolve(self, name: str) -> Any:
        service = self._services.get(name)
        if not service: raise ServiceException(f"{name} not found")
        return service

groq_client = Groq(api_key=config.groq_key)
session_manager = SessionManager()
event_bus = EventBus()
queue_manager = QueueManager()
metrics = MetricsCollector()
container = Container()

queue_manager.start()

class AIService(Service):
    def name(self) -> str: return "ai_service"
    def ask(self, user: User, prompt: str) -> str:
        messages = [{"role": "system", "content": f"Bot: SATRIA. User: {user.full_name}. Role: {user.role.value}. Speak casually."}]
        messages.append({"role": "user", "content": prompt})
        try:
            res = groq_client.chat.completions.create(model="llama-3.1-8b-instant", messages=messages)
            metrics.increment("ai_requests")
            return res.choices[0].message.content
        except Exception as e: raise AIException(str(e))

class UserService(Service):
    def __init__(self, repo: UserRepository) -> None: self._repo = repo
    def name(self) -> str: return "user_service"
    def register(self, dto: RegisterUserDTO) -> User:
        existing = self._repo.find_by_telegram_id(dto.telegram_id)
        if existing: return existing
        user = User(IdGenerator.generate(), dto.telegram_id, dto.full_name, dto.username, RoleHelper.get_role(dto.telegram_id, config.admin_id), Clock.now())
        self._repo.save(user)
        event_bus.publish(EventType.USER_REGISTERED.value, user)
        return user

class ReportService(Service):
    def __init__(self, repo: ReportRepository) -> None: self._repo = repo
    def name(self) -> str: return "report_service"
    def create(self, dto: CreateReportDTO) -> CitizenReport:
        report = CitizenReport(IdGenerator.generate(), dto.user_id, dto.report_type, dto.content, ApprovalStatus.PENDING, Clock.now())
        self._repo.save(report)
        event_bus.publish(EventType.REPORT_CREATED.value, report)
        metrics.increment("reports")
        return report

class KasService(Service):
    def __init__(self, repo: KasRepository, approval_repo: ApprovalRepository) -> None:
        self._repo = repo
        self._approval_repo = approval_repo
    def name(self) -> str: return "kas_service"
    def submit(self, dto: CreateKasDTO) -> KasTransaction:
        trx = KasTransaction(IdGenerator.generate(), dto.user_id, dto.full_name, dto.category, dto.description, dto.amount, ApprovalStatus.PENDING, dto.photo_file_id, Clock.now())
        self._repo.save(trx)
        req = ApprovalRequest(IdGenerator.generate(), trx.id, dto.user_id, "KAS", Clock.now())
        self._approval_repo.save(req)
        event_bus.publish(EventType.PAYMENT_SUBMITTED.value, trx)
        metrics.increment("kas_submissions")
        return trx

class ApprovalService(Service):
    def __init__(self, kas_repo: KasRepository) -> None: self._kas_repo = kas_repo
    def name(self) -> str: return "approval_service"
    def approve(self, id: str) -> Optional[KasTransaction]:
        trx = self._kas_repo.find_by_id(id)
        if not trx: return None
        trx.status = ApprovalStatus.APPROVED
        self._kas_repo.save(trx)
        event_bus.publish(EventType.APPROVAL_APPROVED.value, trx)
        return trx
    def reject(self, id: str) -> Optional[KasTransaction]:
        trx = self._kas_repo.find_by_id(id)
        if not trx: return None
        trx.status = ApprovalStatus.REJECTED
        self._kas_repo.save(trx)
        event_bus.publish(EventType.APPROVAL_REJECTED.value, trx)
        return trx

class NotificationService(Service):
    def __init__(self, bot: telebot.TeleBot) -> None: self._bot = bot
    def name(self) -> str: return "notification_service"
    def send(self, user_id: str, text: str) -> None:
        try: self._bot.send_message(user_id, text)
        except: pass

class BroadcastService(Service):
    def __init__(self, repo: BroadcastRepository, users: UserRepository, bot: telebot.TeleBot) -> None:
        self._repo = repo
        self._users = users
        self._bot = bot
    def name(self) -> str: return "broadcast_service"
    def broadcast(self, dto: BroadcastDTO) -> None:
        msg = BroadcastMessage(IdGenerator.generate(), dto.sender_id, dto.message, Clock.now())
        self._repo.save(msg)
        for user in self._users.find_all():
            task = QueueTask(IdGenerator.generate(), "bc", (user.telegram_id, dto.message), self._send)
            queue_manager.submit(task)
    def _send(self, payload: Any) -> None:
        tid, text = payload
        try: self._bot.send_message(tid, text)
        except: pass

class SpamProtectionService(Service):
    def __init__(self) -> None:
        self._tracker: Dict[str, List[float]] = {}
        self._lock = threading.RLock()
    def name(self) -> str: return "spam_service"
    def is_spam(self, user_id: str) -> bool:
        now = time.time()
        with self._lock:
            self._tracker.setdefault(user_id, [])
            ts = self._tracker[user_id]
            ts[:] = [t for t in ts if now - t < 60]
            ts.append(now)
            return len(ts) > 10

container.register("user_service", UserService(users_repository))
container.register("ai_service", AIService(history_store))
container.register("report_service", ReportService(reports_repository))
container.register("kas_service", KasService(kas_repository, approval_repository))
container.register("approval_service", ApprovalService(kas_repository))
container.register("notification_service", NotificationService(bot))
container.register("broadcast_service", BroadcastService(broadcast_repository, users_repository, bot))
container.register("spam_service", SpamProtectionService())
class ReportingEngine:
    def __init__(self, kas_repo: KasRepository, reports_repo: ReportRepository) -> None:
        self._kas_repo = kas_repo
        self._reports_repo = reports_repo
    def get_kas_report(self) -> Dict[str, Any]:
        all_transactions = self._kas_repo.find_all()
        report = {"total": 0, "categories": {}}
        for trx in all_transactions:
            if trx.status == ApprovalStatus.APPROVED:
                report["total"] += trx.amount
                report["categories"][trx.category] = report["categories"].get(trx.category, 0) + trx.amount
        return report
    def get_activity_report(self) -> Dict[str, Any]:
        reports = self._reports_repo.find_all()
        return {"total_reports": len(reports), "pending": len([r for r in reports if r.status == ApprovalStatus.PENDING])}

class BusinessRulePolicy:
    @staticmethod
    def validate_kas_amount(amount: int) -> bool:
        return 10000 <= amount <= 10000000
    @staticmethod
    def validate_report_content(content: str) -> bool:
        return 10 <= len(content) <= 1000
    @staticmethod
    def is_urgent(content: str) -> bool:
        urgent_keywords = ["darurat", "bencana", "kebakaran", "kriminal", "medis"]
        return any(keyword in content.lower() for keyword in urgent_keywords)

class WorkflowOrchestrator:
    def __init__(self, container: Container) -> None:
        self._container = container
    def handle_payment_submission(self, trx: KasTransaction) -> None:
        approval_service = self._container.resolve("approval_service")
        notification_service = self._container.resolve("notification_service")
        notification_service.send(config.admin_id, f"Approval Required: {trx.id} from {trx.full_name}")
    def handle_report_creation(self, report: CitizenReport) -> None:
        notification_service = self._container.resolve("notification_service")
        if BusinessRulePolicy.is_urgent(report.content):
            notification_service.send(config.admin_id, f"URGENT REPORT: {report.content}")
            if config.group_id:
                notification_service.send(config.group_id, f"URGENT ALERT: {report.content}")

class NotificationOrchestrator:
    def __init__(self, container: Container) -> None:
        self._container = container
    def process_mention_notification(self, text: str, original_sender_name: str) -> None:
        user_repo = self._container.resolve("users_repository")
        ai_service = self._container.resolve("ai_service")
        notification_service = self._container.resolve("notification_service")
        usernames = re.findall(r"@(\w+)", text)
        for username in usernames:
            user = user_repo.find_by_username(username)
            if user:
                context_data = f"Sender: {original_sender_name}. Message: {text}"
                ai_notification = ai_service.ask(user, f"Draft a concise notification message for {user.full_name} stating they were mentioned in a report. Context: {context_data}")
                notification_service.send(user.telegram_id, ai_notification)

class KasAggregationService(Service):
    def __init__(self, kas_repo: KasRepository) -> None:
        self._kas_repo = kas_repo
    def name(self) -> str: return "kas_aggregation_service"
    def get_summary_formatted(self) -> str:
        all_trx = self._kas_repo.find_all()
        summary: Dict[str, int] = {}
        total = 0
        for trx in all_trx:
            if trx.status == ApprovalStatus.APPROVED:
                total += trx.amount
                summary[trx.category] = summary.get(trx.category, 0) + trx.amount
        lines = [f"Total Kas: Rp{total:,}"]
        for cat, val in summary.items():
            lines.append(f"{cat}: Rp{val:,}")
        return "\n".join(lines)

class ApprovalWorkflowEngine:
    def __init__(self, container: Container) -> None:
        self._container = container
    def run_approval_process(self, transaction_id: str, approved: bool) -> None:
        approval_service = self._container.resolve("approval_service")
        notification_service = self._container.resolve("notification_service")
        if approved:
            trx = approval_service.approve(transaction_id)
            if trx: notification_service.send(trx.user_id, "Your kas transaction was approved.")
        else:
            trx = approval_service.reject(transaction_id)
            if trx: notification_service.send(trx.user_id, "Your kas transaction was rejected.")

class SecurityMonitorService(Service):
    def name(self) -> str: return "security_monitor"
    def check_auth(self, user: User, required_role: UserRole) -> bool:
        return user.role == required_role

class BusinessRuleEngine:
    def __init__(self, container: Container) -> None:
        self._container = container
    def evaluate_transaction(self, dto: CreateKasDTO) -> bool:
        return BusinessRulePolicy.validate_kas_amount(dto.amount)
    def evaluate_report(self, dto: CreateReportDTO) -> bool:
        return BusinessRulePolicy.validate_report_content(dto.content)

reporting_engine = ReportingEngine(kas_repository, reports_repository)
workflow_orchestrator = WorkflowOrchestrator(container)
notification_orchestrator = NotificationOrchestrator(container)
kas_aggregation_service = KasAggregationService(kas_repository)
approval_workflow_engine = ApprovalWorkflowEngine(container)
business_rule_engine = BusinessRuleEngine(container)

container.register("reporting_engine", reporting_engine)
container.register("workflow_orchestrator", workflow_orchestrator)
container.register("notification_orchestrator", notification_orchestrator)
container.register("kas_aggregation_service", kas_aggregation_service)
container.register("approval_workflow_engine", approval_workflow_engine)
container.register("business_rule_engine", business_rule_engine)

event_bus.subscribe(EventType.PAYMENT_SUBMITTED.value, workflow_orchestrator.handle_payment_submission)
event_bus.subscribe(EventType.REPORT_CREATED.value, workflow_orchestrator.handle_report_creation)
# --- BOT COMMANDS & MESSAGE DISPATCHER ---

class CommandHandler:
    def __init__(self, container: Container):
        self.container = container
        self.bot = telebot.TeleBot(config.bot_token)
        self.users = container.resolve("user_service")
        self.ai = container.resolve("ai_service")
        self.reports = container.resolve("report_service")
        self.notif = container.resolve("notification_service")
        self.orchestrator = container.resolve("notification_orchestrator")
        self.kas_service = container.resolve("kas_service")
        self.kas_agg = container.resolve("kas_aggregation_service")

    def setup(self):
        @self.bot.message_handler(commands=['start'])
        def start(msg):
            self.users.register(RegisterUserDTO(str(msg.from_user.id), msg.from_user.first_name, msg.from_user.username or ""))
            self.bot.reply_to(msg, "SATRIA Enterprise v2.0 Aktif.")

        @self.bot.message_handler(commands=['kas'])
        def kas_summary(msg):
            self.bot.reply_to(msg, self.kas_agg.get_summary_formatted())

        @self.bot.message_handler(func=lambda m: True, content_types=['text', 'photo'])
        def main_handler(msg):
            user = self.users.register(RegisterUserDTO(str(msg.from_user.id), msg.from_user.first_name, msg.from_user.username or ""))
            text = msg.text or msg.caption or ""
            
            # 1. LOGIKA MENTION & LAPORAN
            if any(k in text.lower() for k in ["lapor", "keluhan", "ada masalah"]):
                report = self.reports.create(CreateReportDTO(str(user.id), ReportType.LAPORAN, text))
                self.bot.reply_to(msg, "✅ Laporan diterima.")
                
                # Posting ke grup
                if config.group_id:
                    self.notif.send(config.group_id, f"📢 Laporan dari {user.full_name}:\n{text}")
                
                # Logika Mentions (Japri + Group)
                usernames = re.findall(r"@(\w+)", text)
                for uname in usernames:
                    target = container.resolve("user_service")._repo.find_by_username(uname)
                    if target:
                        # Buat pesan via AI
                        ai_msg = self.ai.ask(target, f"Buatkan notifikasi untuk {target.full_name} terkait laporan: {text}")
                        # Japri
                        self.notif.send(target.telegram_id, f"🔔 Notifikasi Sistem:\n{ai_msg}")
                        # Kirim juga ke group sesuai request
                        if config.group_id:
                            self.notif.send(config.group_id, f"📩 Notifikasi untuk @{uname}:\n{ai_msg}")

            # 2. LOGIKA AI CHAT
            elif f"@{self.bot.get_me().username}" in text or msg.chat.type == "private":
                response = self.ai.ask(user, text)
                self.bot.reply_to(msg, response)

    def run(self):
        logger.info("SATRIA Enterprise starting polling...")
        self.bot.infinity_polling(skip_pending=True)

# --- APPLICATION ENTRY POINT ---

if __name__ == "__main__":
    try:
        handler = CommandHandler(container)
        handler.setup()
        handler.run()
    except Exception as e:
        logger.error(f"Critical System Failure: {e}")
