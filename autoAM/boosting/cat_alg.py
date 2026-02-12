import pandas as pd
import numpy as np
from catboost import CatBoostRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

# 1. Load Data
print("Loading data...")
df = pd.read_csv('combined.tsv', sep='\t')

# 2. Rename Columns
column_mapping = {
    'id': 'id',
    'brand': 'Make',
    'model': 'Model',
    'price': 'Price',
    'taxed': 'Taxed',
    'year': 'Year',
    'Անվահեծերը': 'Wheel_Size',
    'Գույնը': 'Color',
    'Դռների քանակը': 'Door_Count',
    'Թափքը': 'Body_Type',
    'Հեռահարությունը': 'Range_Km',
    'Ձիաուժը': 'Horsepower',
    'Ղեկը': 'Steering',
    'Մարտկոցի տարողունակությունը կվտ': 'Battery_Capacity',
    'Մխոցների քանակը': 'Cylinders',
    'Մոդիֆիկացիան': 'Trim',
    'Շարժիչը': 'Fuel_Type',
    'Շարժիչի ծավալը': 'Engine_Volume',
    'Սրահի գույնը': 'Interior_Color',
    'Վազքը': 'Mileage',
    'Վիճակը': 'Condition',
    'Փոխանցման տուփը': 'Transmission',
    'Քարշակը': 'Drive_Type',
    'էլ․ շարժիչների քանակը': 'Electric_Motor_Count'
}

df = df.rename(columns=column_mapping)
df = df.drop(columns=['id'])

# --- DATA CLEANING (Robust Version) ---
print("Cleaning data...")

def clean_numeric(series, remove_chars=None):
    s = series.astype(str)
    if remove_chars:
        for char in remove_chars:
            s = s.str.replace(char, '', regex=False)
    # Remove any non-numeric characters except dots
    s = s.str.replace(r'[^\d.]+', '', regex=True)
    return pd.to_numeric(s, errors='coerce')

# Clean Numerics
df['Horsepower'] = clean_numeric(df['Horsepower'], [' hp', 'hp'])
df['Range_Km'] = clean_numeric(df['Range_Km'], [' կմ', ' km', ' '])
df['Mileage'] = clean_numeric(df['Mileage'], [' կմ', ' km', ' '])
df['Battery_Capacity'] = clean_numeric(df['Battery_Capacity'], ['kvt', ' kvt', 'kWh', ' '])
df['Engine_Volume'] = clean_numeric(df['Engine_Volume'], ['L', ' l'])
df['Wheel_Size'] = clean_numeric(df['Wheel_Size'], ['"', "'"])
df['Door_Count'] = clean_numeric(df['Door_Count']) 
df['Cylinders'] = clean_numeric(df['Cylinders'])

# Feature Engineering
df['Car_Age'] = 2025 - df['Year']
df = df[df['Price'] > 2000]  # Filter junk prices
df = df[df['Price'] < 80000]  # Filter junk prices
df['Log_Price'] = np.log1p(df['Price'])

# --- CATEGORICAL FIX (The Solultion) ---

# 1. Define Categorical Columns
cat_features = [
    'Make', 'Model', 'Taxed', 'Color', 
    'Body_Type', 'Steering', 'Trim', 'Fuel_Type', 
    'Interior_Color', 'Condition', 'Transmission', 'Drive_Type'
]

# 2. STRICT Cleanup Loop
for col in cat_features:
    # Fill NaN with "Unknown" BEFORE converting to string
    df[col] = df[col].fillna("Unknown")
    # Force convert to string (to handle mixed types like 1.0 vs "1")
    df[col] = df[col].astype(str)
    # Clean up empty strings or "nan" strings if they survived
    df.loc[df[col].isin(['nan', 'NaN', '']), col] = "Unknown"

# Fill numeric NaNs with -1 (Standard for Trees)
num_features = ['Horsepower', 'Range_Km', 'Mileage', 'Battery_Capacity', 'Engine_Volume', 'Wheel_Size', 'Car_Age', 'Door_Count', 'Cylinders']
for col in num_features:
    df[col] = df[col].fillna(-1)

# --- TRAINING ---

X = df.drop(columns=['Price', 'Log_Price'])
y = df['Log_Price']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print(f"Starting training on {len(X_train)} cars...")

model = CatBoostRegressor(
    depth=8,              # The "Smart" setting
    learning_rate=0.08,   # slightly lower than 0.1 for safety
    l2_leaf_reg=5,        # Good regularization
    iterations=4000,      # Give it a bit more time to settle
    loss_function='RMSE',
    verbose=500
)

model.fit(X_train, y_train, cat_features=cat_features)

# Evaluate
predictions_log = model.predict(X_test)
predictions_real = np.expm1(predictions_log)
y_test_real = np.expm1(y_test)

mae = mean_absolute_error(y_test_real, predictions_real)
r2 = r2_score(y_test_real, predictions_real)


model.save_model("car_price_model2.cbm")
print(f"\n--- SUCCESS ---")
print(f"Mean Absolute Error: ${mae:.2f}")
print(f"R2 Score: {r2:.2f}")