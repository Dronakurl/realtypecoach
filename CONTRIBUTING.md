# Contributing

Welcome! This is a hobby project focused on typing analysis. Whether you're fixing a bug, adding a feature, or just exploring the code - we're glad to have you!

## Development Commands

This project uses `just` for development workflows. Install `just` from: https://just.systems/

### Available Commands

```bash
# Run the application
just run

# Run all tests
just test-all

# Clean cache and kill running instances
just clean

# Kill all running instances
just kill

# Check running status
just status

# Clean, check, and run
just rebuild

# Full reset (kill, clean, reset database, run)
just full

# Test imports
just test-imports
```

## Getting Started

1. Fork and clone the repository
2. Make your changes
3. Test with `just test-all`
4. Submit a pull request

Happy coding!
