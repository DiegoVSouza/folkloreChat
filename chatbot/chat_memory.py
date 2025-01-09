from datetime import timedelta
from .models import ChatHistory
from django.utils.timezone import now

class ChatMemory:
    def save_message(self, user_id, character, role, message):
        ChatHistory.objects.create(user_id=user_id, character=character, role=role, message=message)

    def get_chat_history(self, user_id, character):
        history = ChatHistory.objects.filter(user_id=user_id, character=character).order_by('timestamp')
        return [{"role": h.role, "content": h.message} for h in history]

    def get_summary(self, user_id,character):
        summary = ChatHistory.objects.filter(user_id=user_id, character=character, role="summary").last()
        return {"role": summary.role, "content": summary.message} if summary else None

    def save_summary(self, user_id, character, summary):
        ChatHistory.objects.create(user_id=user_id, role="summary", character=character, message=summary)

    def clean_old_messages(self):
        expiration_date = now() - timedelta(days=3)
        ChatHistory.objects.filter(timestamp__lt=expiration_date).delete()

    def clean_messages(self):
        ChatHistory.objects.all().delete()
