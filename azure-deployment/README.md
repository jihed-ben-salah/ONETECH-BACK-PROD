# Azure Deployment for OneTeach Backend

This directory contains the necessary files to deploy the OneTeach Backend application to Azure Container Instances (ACI).

## Files

- `aci-template.json` - ARM template for Azure Container Instances deployment
- `aci-parameters.json` - Parameters file for the ARM template (template - update with your values)
- `deploy.sh` - Bash deployment script (for Linux/macOS/WSL)
- `deploy.ps1` - PowerShell deployment script (for Windows)

## Prerequisites

1. **Azure CLI**: Install the Azure CLI from [here](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
2. **Docker**: Ensure Docker is installed and running
3. **Azure Subscription**: You need an active Azure subscription
4. **Google API Key**: For the Gemini AI functionality

## Quick Deployment (Recommended)

### For Windows (PowerShell):
```powershell
# Navigate to the project root
cd "c:\MY FILES\Dev\one tech\ONETECH-BACK-PROD"

# Login to Azure
az login

# Run the deployment script
.\azure-deployment\deploy.ps1
```

### For Linux/macOS/WSL (Bash):
```bash
# Navigate to the project root
cd "/c/MY FILES/Dev/one tech/ONETECH-BACK-PROD"

# Login to Azure
az login

# Make the script executable
chmod +x azure-deployment/deploy.sh

# Run the deployment script
./azure-deployment/deploy.sh
```

## Manual Deployment

If you prefer to deploy manually or customize the deployment:

1. **Login to Azure:**
   ```bash
   az login
   ```

2. **Create a resource group:**
   ```bash
   az group create --name onetech-backend-rg --location "East US"
   ```

3. **Create Azure Container Registry:**
   ```bash
   az acr create --resource-group onetech-backend-rg --name onetechregistry --sku Basic --admin-enabled true
   ```

4. **Build and push the Docker image:**
   ```bash
   # Get ACR login server
   ACR_LOGIN_SERVER=$(az acr show --name onetechregistry --resource-group onetech-backend-rg --query "loginServer" --output tsv)
   
   # Login to ACR
   az acr login --name onetechregistry
   
   # Build and push
   docker build -t $ACR_LOGIN_SERVER/onetech-backend:latest .
   docker push $ACR_LOGIN_SERVER/onetech-backend:latest
   ```

5. **Update the parameters file:**
   Edit `aci-parameters.json` with your actual values:
   - Replace `YOUR_REGISTRY` with your ACR name
   - Replace `YOUR_REGISTRY_USERNAME` and `YOUR_REGISTRY_PASSWORD` with ACR credentials
   - Replace `YOUR_DJANGO_SECRET_KEY` with a secure secret key
   - Replace `YOUR_GOOGLE_API_KEY` with your Google API key

6. **Deploy using ARM template:**
   ```bash
   az deployment group create \
     --resource-group onetech-backend-rg \
     --template-file azure-deployment/aci-template.json \
     --parameters @azure-deployment/aci-parameters.json
   ```

## Configuration

### Environment Variables

The deployment sets up the following environment variables:

- `DJANGO_SECRET_KEY`: Django secret key for security
- `DEBUG`: Set to "false" for production
- `GOOGLE_API_KEY`: Your Google API key for Gemini AI
- `GEMINI_MODEL`: AI model name (default: "gemini-2.5-pro")

### Resource Allocation

The container is configured with:
- **CPU**: 1.0 core
- **Memory**: 2.0 GB
- **Port**: 8000 (HTTP)

## Post-Deployment

After successful deployment, you'll get:

1. **Public IP Address**: Direct access to your application
2. **FQDN**: Fully qualified domain name for easier access
3. **Logs**: Access to container logs for debugging

### Useful Commands

**Check container status:**
```bash
az container show --resource-group onetech-backend-rg --name onetech-backend
```

**View logs:**
```bash
az container logs --resource-group onetech-backend-rg --name onetech-backend
```

**Restart container:**
```bash
az container restart --resource-group onetech-backend-rg --name onetech-backend
```

**Clean up resources:**
```bash
az group delete --name onetech-backend-rg --yes --no-wait
```

## Troubleshooting

### Common Issues

1. **Registry name not unique**: The ACR name must be globally unique. Change the `AcrName` in the script.

2. **Insufficient permissions**: Ensure your Azure account has Contributor access to the subscription.

3. **Docker build fails**: Check that all dependencies in `requirements.txt` are available.

4. **Container fails to start**: Check the logs using the command above.

### Health Check

The application includes a health check endpoint. The container will be marked as unhealthy if the application doesn't respond within the configured timeout.

## Security Considerations

- The deployment uses secure string parameters for sensitive data
- CORS is configured for cross-origin requests
- The application runs with non-root privileges in the container
- SSL/HTTPS is not configured by default - consider using Azure Application Gateway or Azure Front Door for production

## Scaling

For production use, consider:
- Using Azure Container Apps for better scaling capabilities
- Implementing Azure Database for PostgreSQL instead of SQLite
- Adding Azure Application Gateway for SSL termination
- Setting up monitoring with Azure Monitor

## Cost Optimization

- The current configuration uses Basic SKU for ACR and minimal resources for ACI
- Consider using Azure Container Apps or AKS for cost-effective scaling in production
- Monitor usage and adjust resource allocation as needed
