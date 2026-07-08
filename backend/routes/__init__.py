from .auth import auth_bp
from .course import course_bp
from .document import document_bp
from .chat import chat_bp
from .task import task_bp
from .plan import plan_bp
from .agent import agent_bp

__all__ = ['auth_bp', 'course_bp', 'document_bp', 'chat_bp', 'task_bp', 'plan_bp', 'agent_bp']
