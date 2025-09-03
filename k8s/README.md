# Kubernetes Deployment

This directory contains Kubernetes manifests for deploying the Site Analyser as a daily batch job.

## Files

- `namespace.yaml` - Creates the site-analyser namespace
- `secret.yaml` - Contains API keys for AI services
- `configmap.yaml` - Configuration for the analysis job
- `job.yaml` - One-time job execution
- `cronjob.yaml` - Daily scheduled job execution

## Deployment Steps

1. **Create namespace:**
   ```bash
   kubectl apply -f k8s/namespace.yaml
   ```

2. **Update secrets with your API keys:**
   ```bash
   # Encode your API keys
   echo -n "your-openai-api-key" | base64
   echo -n "your-anthropic-api-key" | base64
   
   # Edit secret.yaml and add the base64 encoded keys
   kubectl apply -f k8s/secret.yaml
   ```

3. **Update configuration:**
   Edit `k8s/configmap.yaml` to update the list of URLs and other settings.
   ```bash
   kubectl apply -f k8s/configmap.yaml
   ```

4. **Deploy the CronJob:**
   ```bash
   kubectl apply -f k8s/cronjob.yaml
   ```

## Running a One-time Job

To run the analysis immediately instead of waiting for the scheduled time:

```bash
kubectl apply -f k8s/job.yaml
```

## Monitoring

View running jobs:
```bash
kubectl get jobs -n site-analyser
kubectl get cronjobs -n site-analyser
```

Check job logs:
```bash
kubectl logs -n site-analyser job/site-analyser-job
```

## Configuration Updates

To update the analysis configuration:

1. Edit `k8s/configmap.yaml`
2. Apply changes: `kubectl apply -f k8s/configmap.yaml`
3. The next scheduled job will use the new configuration

## Security Notes

- Jobs run as non-root user (UID 1000)
- Read-only root filesystem where possible
- Resource limits prevent resource exhaustion
- Secrets are mounted as environment variables