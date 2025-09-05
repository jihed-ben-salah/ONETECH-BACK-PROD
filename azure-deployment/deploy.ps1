# Azure Container Registry and ACI Deployment Script (PowerShell)
# This script builds and deploys the OneTeach Backend to Azure Container Instances

param(
    [string]$ResourceGroup = "onetech-backend-rg",
    [string]$Location = "France Central",
    [string]$AcrName = "onetechregistry",  # Must be globally unique
    [string]$ContainerGroupName = "onetech-backend",
    [string]$ImageName = "onetech-backend",
    [string]$ImageTag = "latest"
)

# Error handling
$ErrorActionPreference = "Stop"

# Check if Azure CLI is installed
try {
    az version | Out-Null
}
catch {
    Write-Error "Azure CLI is not installed. Please install it first."
    Write-Host "Visit: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
}

# Check if user is logged in
try {
    az account show | Out-Null
}
catch {
    Write-Error "Please log in to Azure CLI first:"
    Write-Host "az login"
    exit 1
}

Write-Host "🚀 Starting Azure deployment for OneTeach Backend..." -ForegroundColor Green

# Create resource group
Write-Host "📦 Creating resource group..." -ForegroundColor Yellow
az group create --name $ResourceGroup --location $Location

# Create Azure Container Registry
Write-Host "🏭 Creating Azure Container Registry..." -ForegroundColor Yellow
az acr create --resource-group $ResourceGroup --name $AcrName --sku Basic --admin-enabled true

# Get ACR login server
$AcrLoginServer = az acr show --name $AcrName --resource-group $ResourceGroup --query "loginServer" --output tsv
Write-Host "Registry server: $AcrLoginServer" -ForegroundColor Cyan

# Log in to ACR
Write-Host "🔐 Logging in to Azure Container Registry..." -ForegroundColor Yellow
az acr login --name $AcrName

# Build and push image
Write-Host "🔨 Building and pushing Docker image..." -ForegroundColor Yellow
docker build -t "$AcrLoginServer/$ImageName`:$ImageTag" .
docker push "$AcrLoginServer/$ImageName`:$ImageTag"

# Get ACR credentials
$AcrUsername = az acr credential show --name $AcrName --resource-group $ResourceGroup --query "username" --output tsv
$AcrPassword = az acr credential show --name $AcrName --resource-group $ResourceGroup --query "passwords[0].value" --output tsv

# Generate a strong Django secret key
$DjangoSecretKey = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes([System.Guid]::NewGuid().ToString() + [System.Guid]::NewGuid().ToString()))

# Prompt for Google API key
Write-Host ""
Write-Host "🔑 Please enter your Google API key for Gemini:" -ForegroundColor Yellow
$GoogleApiKeyPlain = Read-Host

if ([string]::IsNullOrEmpty($GoogleApiKeyPlain)) {
    Write-Error "❌ Google API key is required!"
    exit 1
}

Write-Host "✅ Google API key received" -ForegroundColor Green

# Deploy to Azure Container Instances
Write-Host "🚀 Deploying to Azure Container Instances..." -ForegroundColor Yellow
az deployment group create `
    --resource-group $ResourceGroup `
    --template-file "azure-deployment/aci-template.json" `
    --parameters `
        containerGroupName=$ContainerGroupName `
        containerImageName="$AcrLoginServer/$ImageName`:$ImageTag" `
        registryServer=$AcrLoginServer `
        registryUsername=$AcrUsername `
        registryPassword=$AcrPassword `
        djangoSecretKey=$DjangoSecretKey `
        googleApiKey=$GoogleApiKeyPlain `
        debug="false"

# Get the deployment outputs
Write-Host "📋 Getting deployment information..." -ForegroundColor Yellow
$ContainerIp = az deployment group show --resource-group $ResourceGroup --name aci-template --query "properties.outputs.containerIPv4Address.value" --output tsv
$ContainerFqdn = az deployment group show --resource-group $ResourceGroup --name aci-template --query "properties.outputs.containerFQDN.value" --output tsv

Write-Host ""
Write-Host "✅ Deployment completed successfully!" -ForegroundColor Green
Write-Host "🌐 Your application is available at:" -ForegroundColor Cyan
Write-Host "   IP Address: http://$ContainerIp`:8000" -ForegroundColor White
Write-Host "   FQDN: http://$ContainerFqdn`:8000" -ForegroundColor White
Write-Host ""
Write-Host "📊 To check the status of your container:" -ForegroundColor Yellow
Write-Host "   az container show --resource-group $ResourceGroup --name $ContainerGroupName" -ForegroundColor White
Write-Host ""
Write-Host "📜 To view logs:" -ForegroundColor Yellow
Write-Host "   az container logs --resource-group $ResourceGroup --name $ContainerGroupName" -ForegroundColor White
Write-Host ""
Write-Host "🗑️  To clean up resources:" -ForegroundColor Yellow
Write-Host "   az group delete --name $ResourceGroup --yes --no-wait" -ForegroundColor White
