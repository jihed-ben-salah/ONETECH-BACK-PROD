#!/bin/bash

# Azure Container Registry and ACI Deployment Script
# This script builds and deploys the OneTeach Backend to Azure Container Instances

set -e

# Configuration variables - Update these with your values
RESOURCE_GROUP="onetech-backend-rg"
LOCATION="East US"
ACR_NAME="onetechregistry"  # Must be globally unique
CONTAINER_GROUP_NAME="onetech-backend"
IMAGE_NAME="onetech-backend"
IMAGE_TAG="latest"

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "Azure CLI is not installed. Please install it first."
    echo "Visit: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Check if user is logged in
if ! az account show &> /dev/null; then
    echo "Please log in to Azure CLI first:"
    echo "az login"
    exit 1
fi

echo "🚀 Starting Azure deployment for OneTeach Backend..."

# Create resource group
echo "📦 Creating resource group..."
az group create \
    --name $RESOURCE_GROUP \
    --location "$LOCATION"

# Create Azure Container Registry
echo "🏭 Creating Azure Container Registry..."
az acr create \
    --resource-group $RESOURCE_GROUP \
    --name $ACR_NAME \
    --sku Basic \
    --admin-enabled true

# Get ACR login server
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query "loginServer" --output tsv)
echo "Registry server: $ACR_LOGIN_SERVER"

# Log in to ACR
echo "🔐 Logging in to Azure Container Registry..."
az acr login --name $ACR_NAME

# Build and push image
echo "🔨 Building and pushing Docker image..."
docker build -t $ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG .
docker push $ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query "username" --output tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query "passwords[0].value" --output tsv)

# Generate a strong Django secret key
DJANGO_SECRET_KEY=$(openssl rand -base64 32)

# Prompt for Google API key
echo ""
echo "🔑 Please enter your Google API key for Gemini:"
read -s GOOGLE_API_KEY

if [ -z "$GOOGLE_API_KEY" ]; then
    echo "❌ Google API key is required!"
    exit 1
fi

# Deploy to Azure Container Instances
echo "🚀 Deploying to Azure Container Instances..."
az deployment group create \
    --resource-group $RESOURCE_GROUP \
    --template-file azure-deployment/aci-template.json \
    --parameters \
        containerGroupName=$CONTAINER_GROUP_NAME \
        containerImageName=$ACR_LOGIN_SERVER/$IMAGE_NAME:$IMAGE_TAG \
        registryServer=$ACR_LOGIN_SERVER \
        registryUsername=$ACR_USERNAME \
        registryPassword=$ACR_PASSWORD \
        djangoSecretKey="$DJANGO_SECRET_KEY" \
        googleApiKey="$GOOGLE_API_KEY" \
        debug="false"

# Get the deployment outputs
echo "📋 Getting deployment information..."
CONTAINER_IP=$(az deployment group show \
    --resource-group $RESOURCE_GROUP \
    --name aci-template \
    --query "properties.outputs.containerIPv4Address.value" \
    --output tsv)

CONTAINER_FQDN=$(az deployment group show \
    --resource-group $RESOURCE_GROUP \
    --name aci-template \
    --query "properties.outputs.containerFQDN.value" \
    --output tsv)

echo ""
echo "✅ Deployment completed successfully!"
echo "🌐 Your application is available at:"
echo "   IP Address: http://$CONTAINER_IP:8000"
echo "   FQDN: http://$CONTAINER_FQDN:8000"
echo ""
echo "📊 To check the status of your container:"
echo "   az container show --resource-group $RESOURCE_GROUP --name $CONTAINER_GROUP_NAME"
echo ""
echo "📜 To view logs:"
echo "   az container logs --resource-group $RESOURCE_GROUP --name $CONTAINER_GROUP_NAME"
echo ""
echo "🗑️  To clean up resources:"
echo "   az group delete --name $RESOURCE_GROUP --yes --no-wait"
