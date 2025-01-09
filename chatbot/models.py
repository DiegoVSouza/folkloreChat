from django.db import models

class ChatHistory(models.Model):
    user_id = models.CharField(max_length=255)  
    role = models.CharField(max_length=50) 
    character = models.CharField(max_length=50) 
    message = models.TextField()  
    timestamp = models.DateTimeField(auto_now_add=True)  

    class Meta:
        verbose_name = "Chat History"
        verbose_name_plural = "Chat Histories"

    def __str__(self):
        return f"{self.user_id} - {self.role}: {self.message[:50]}"
