"""Machine learning pipeline architecture using scikit-learn."""

from typing import List, Tuple
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# Canonical feature lists
NUMERIC_FEATURES: List[str] = [
    "recency_days",
    "frequency",
    "monetary_value",
    "average_order_value",
    "purchase_interval_avg",
    "purchase_interval_std",
    "return_rate",
    "tenure_days",
]

CATEGORICAL_FEATURES: List[str] = [
    "country",
]


def build_preprocessing_pipeline() -> ColumnTransformer:
    """Build scikit-learn ColumnTransformer for numerical scaling and categorical encoding."""
    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="Unknown")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, NUMERIC_FEATURES),
            ("cat", categorical_transformer, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )
    return preprocessor


def build_model_pipeline(
    model_type: str = "random_forest",
    random_state: int = 42,
) -> Pipeline:
    """Construct complete scikit-learn Pipeline with preprocessor and classifier.

    Args:
        model_type: Classifier type ('logistic_regression' or 'random_forest').
        random_state: Seed for reproducible initialization.

    Returns:
        Configured scikit-learn Pipeline.
    """
    preprocessor = build_preprocessing_pipeline()

    if model_type.lower() == "logistic_regression":
        classifier = LogisticRegression(
            class_weight="balanced",
            random_state=random_state,
            max_iter=1000,
            solver="lbfgs",
        )
    elif model_type.lower() == "random_forest":
        classifier = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            min_samples_split=5,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=random_state,
            n_jobs=-1,
        )
    else:
        raise ValueError(f"Unsupported model_type: '{model_type}'. Choose 'logistic_regression' or 'random_forest'.")

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )
