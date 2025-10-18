import numpy as np
import random
import os
# The following imports are often necessary for complete determinism
import warnings # Used below to suppress a potential warning

# The magic number that ensures repeatability
DETERMINISTIC_SEED = 42

def set_all_seeds(seed):
    """
    Sets seeds for all necessary libraries and enforces single-threaded execution 
    to ensure maximum prediction repeatability.
    All major deep learning and ML libraries are included and UNCOMMENTED for maximum effect.
    """
    # 1. Standard Python environment control
    os.environ['PYTHONHASHSEED'] = str(seed)
    random.seed(seed)
    
    # 2. NumPy seed (essential for most ML libraries, including scikit-learn)
    np.random.seed(seed)

    # 3. CRITICAL: Enforce single-threading for underlying numerical libraries.
    # Parallelism in these libraries is a major source of non-determinism.
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['OPENBLAS_NUM_THREADS'] = '1'
    os.environ['MKL_NUM_THREADS'] = '1'
    os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
    os.environ['NUMEXPR_NUM_THREADS'] = '1'
    
    # --- Deep Learning Framework Determinism (ACTIVE) ---
    
    # 4. TensorFlow/Keras Seed 
    try:
        import tensorflow as tf
        tf.random.set_seed(seed)
        # Also consider setting global deterministic behavior if on GPU:
        # tf.config.experimental.enable_op_determinism() 
    except ImportError:
        pass

    # 5. PyTorch Seed 
    try:
        import torch
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
            # Force deterministic algorithms on CUDA (can slow down training/inference)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    except ImportError:
        pass
    
    # --- Ensemble/Scikit-learn Determinism ---

    # 6. Scikit-learn environment setting (Needed if joblib/multiprocessing is used)
    try:
        import joblib
        # Forcing single core execution removes parallel randomness
        joblib.parallel.DEFAULT_N_JOBS = 1 
    except ImportError:
        pass # Joblib is not installed

    # 7. Optional: Suppress a common warning when setting PYTHONHASHSEED
    warnings.filterwarnings("ignore", category=UserWarning, message="A NumPy version might be associated with a different library, potentially leading to instability.")


# Call this function once when your Flask app starts or before loading the model
set_all_seeds(DETERMINISTIC_SEED) 
# ... rest of your model loading and prediction function ...
