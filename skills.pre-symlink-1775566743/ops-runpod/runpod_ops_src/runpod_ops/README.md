# RunPod Operations Package

A modular package for managing GPU instances on RunPod for both training and inference workloads. This package is designed to be used across multiple projects, not just unsloth_wip.

## Features

- **Instance Management**: Create, monitor, and terminate RunPod instances
- **Cost Optimization**: Compare costs across providers and GPU types
- **Training Orchestration**: Distributed training support with multiple strategies
- **Inference Deployment**: Deploy models as API endpoints with autoscaling
- **Real-time Monitoring**: Track GPU utilization, costs, and training progress

## Installation

```bash
# Add to your project's requirements
uv add runpod httpx
```

## Quick Start

### Training a Model

```python
from runpod_ops import TrainingOrchestrator, TrainingConfig

# Configure training
config = TrainingConfig(
    model_name="unsloth/Phi-3.5-mini-instruct",
    model_size="3B",
    dataset_path="path/to/dataset",
    output_path="./output",
    num_epochs=3,
    learning_rate=2e-4
)

# Start training
orchestrator = TrainingOrchestrator()
job = await orchestrator.start_training_job(
    config,
    num_gpus=2,
    spot_instances=True
)

# Monitor progress
status = await orchestrator.get_job_status(job.job_id)
print(f"Training status: {status['status']}")
print(f"Total cost so far: ${status['total_cost']}")
```

### Deploying for Inference

```python
from runpod_ops import InferenceServer

server = InferenceServer()

# Deploy model
endpoint = await server.deploy_model(
    "huggingface/model-name",
    gpu_type="RTX_4090",
    max_batch_size=32
)

# Query endpoint
response = await server.query_endpoint(
    endpoint.endpoint_id,
    "What is the meaning of life?",
    max_tokens=100
)

# Get metrics
metrics = await server.get_endpoint_metrics(endpoint.endpoint_id)
print(f"Cost per request: ${metrics['cost_metrics']['cost_per_request']}")
```

### Cost Comparison

```python
from runpod_ops import CostCalculator

calculator = CostCalculator()

# Compare providers for your workload
comparison = calculator.compare_providers(
    model_size="13B",
    tokens=1_000_000
)

for provider, info in comparison.items():
    print(f"{provider}: ${info['total_cost']} ({info['processing_time_hours']}h)")
```

## Components

### RunPodManager
Core instance management functionality:
- Create/terminate instances
- Configure GPU types and counts
- Handle spot instances
- Track instance costs

### InstanceOptimizer
Intelligent GPU selection:
- Optimize for cost vs speed
- Multi-GPU configurations
- Memory requirement calculations
- Batch size optimization

### CostCalculator
Cross-provider cost analysis:
- RunPod vs Vertex AI vs local
- Monthly budget planning
- Batch processing estimates
- Token-based vs hourly pricing

### InstanceMonitor
Real-time monitoring:
- GPU utilization tracking
- Training progress parsing
- Auto-shutdown on idle
- Cost accumulation

### TrainingOrchestrator
Distributed training management:
- Single and multi-node setups
- DDP/FSDP/DeepSpeed strategies
- Automatic script generation
- Job lifecycle management

### InferenceServer
Production inference deployment:
- vLLM-based serving
- Batch inference support
- Autoscaling configuration
- Performance metrics

## Configuration

Set your RunPod API key:
```bash
export RUNPOD_API_KEY=your_api_key_here
```

## Advanced Usage

### Distributed Training

```python
# Multi-node training
job = await orchestrator.run_distributed_training(
    config,
    num_nodes=4,
    gpus_per_node=2,
    strategy="fsdp"  # or "ddp", "deepspeed"
)
```

### Custom Instance Configuration

```python
from runpod_ops import RunPodManager

manager = RunPodManager()

# Custom instance with specific requirements
instance = await manager.create_instance(
    purpose="training",
    config={
        "gpu_type": "A100_80GB",
        "gpu_count": 2,
        "disk_size": 200,
        "volume_size": 500,
        "image": "custom/image:latest",
        "env": {
            "CUSTOM_VAR": "value"
        },
        "ports": "8888/http,6006/http",  # Jupyter + TensorBoard
    }
)
```

### Monitoring with Callbacks

```python
async def progress_callback(update):
    print(f"GPU: {update['gpu_utilization']}%")
    print(f"Loss: {update.get('training_progress', {}).get('loss', 'N/A')}")
    print(f"Cost: ${update['total_cost']}")

await monitor.monitor_training_job(
    instance_id,
    callback=progress_callback,
    check_interval=30
)
```

## Best Practices

1. **Use Spot Instances**: Save up to 50% on training costs
2. **Monitor GPU Utilization**: Ensure efficient resource usage
3. **Batch Inference**: Maximize throughput for production
4. **Auto-shutdown**: Prevent idle instances from accumulating costs
5. **Compare Providers**: RunPod isn't always cheapest for all workloads

## Integration with Other Projects

This package is designed to be imported by any project needing GPU compute:

```python
# In any project's pyproject.toml
[dependencies]
runpod_ops = { path = "../unsloth_wip/src/runpod_ops" }

# Or install from git
runpod_ops = { git = "https://github.com/your-repo/unsloth_wip.git", subdirectory = "src/runpod_ops" }
```

## License

MIT License - See parent project for details.