from rest_framework import serializers

class ExtractionRequestSerializer(serializers.Serializer):
    document_type = serializers.CharField(required=True)
    file = serializers.FileField(required=True)

class ExtractionResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    data = serializers.DictField()
