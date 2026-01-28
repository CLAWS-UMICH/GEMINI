import torch

# Load the .pth file
checkpoint = torch.load("models/referencemodel.pth", map_location="cpu", weights_only=False)

# What type is it?
print(f"Type: {type(checkpoint)}")

# If it's a dict, print the keys
if isinstance(checkpoint, dict):
    print(f"Keys: {list(checkpoint.keys())}")

    # Check for common keys
    if "model_state_dict" in checkpoint:
        keys = list(checkpoint["model_state_dict"].keys())
        print(f"\nModel layers (first 10): {keys[:10]}")
        print(f"Total layers: {len(keys)}")

    if "state_dict" in checkpoint:
        keys = list(checkpoint["state_dict"].keys())
        print(f"\nModel layers (first 10): {keys[:10]}")
        print(f"Total layers: {len(keys)}")

    if "config" in checkpoint:
        print(f"\nConfig: {checkpoint['config']}")

    if "label_map" in checkpoint or "id2label" in checkpoint:     
        print(f"\nLabels: {checkpoint.get('label_map',
checkpoint.get('id2label'))}")

    if "num_labels" in checkpoint:
        print(f"\nNum labels: {checkpoint['num_labels']}")        

# If it's a full model (not a dict)
else:
    print(f"Full model object: {checkpoint}")
    if hasattr(checkpoint, 'config'):
        print(f"Config: {checkpoint.config}")
    if hasattr(checkpoint, 'num_labels'):
        print(f"Num labels: {checkpoint.num_labels}")