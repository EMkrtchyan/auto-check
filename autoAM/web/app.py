import streamlit as st
import pandas as pd
import numpy as np
from catboost import CatBoostRegressor

# --- CONFIGURATION ---
MODEL_PATH = "car_price_model2.cbm"
DATA_PATH = "combined.tsv"  # We need this to get the lists of Make/Models

st.set_page_config(page_title="Armenia Car Price AI", layout="centered")

# --- LOAD RESOURCES ---
@st.cache_resource
def load_model():
    model = CatBoostRegressor()
    model.load_model(MODEL_PATH)
    return model

@st.cache_data
def load_data():
    # Load data just to get unique values for dropdowns
    df = pd.read_csv(DATA_PATH, sep='\t')
    
    # Rename columns to match training (Minimal cleanup for dropdowns)
    column_mapping = {
        'brand': 'Make', 'model': 'Model', 'taxed': 'Taxed',
        'year': 'Year', 'Անվահեծերը': 'Wheel_Size', 'Գույնը': 'Color',
        'Դռների քանակը': 'Door_Count', 'Թափքը': 'Body_Type',
        'Հեռահարությունը': 'Range_Km', 'Ձիաուժը': 'Horsepower',
        'Ղեկը': 'Steering', 'Մարտկոցի տարողունակությունը կվտ': 'Battery_Capacity',
        'Մխոցների քանակը': 'Cylinders', 'Մոդիֆիկացիան': 'Trim',
        'Շարժիչը': 'Fuel_Type', 'Շարժիչի ծավալը': 'Engine_Volume',
        'Սրահի գույնը': 'Interior_Color', 'Վազքը': 'Mileage',
        'Վիճակը': 'Condition', 'Փոխանցման տուփը': 'Transmission',
        'Քարշակը': 'Drive_Type', 'էլ․ շարժիչների քանակը': 'Electric_Motor_Count'
    }
    df = df.rename(columns=column_mapping)
    
    # Basic cleaning to make dropdowns look nice
    df['Make'] = df['Make'].astype(str)
    df['Model'] = df['Model'].astype(str)
    return df

try:
    model = load_model()
    df = load_data()
    st.success("✅ Model & Data Loaded Successfully")
except Exception as e:
    st.error(f"Error loading resources: {e}")
    st.stop()

# --- SIDEBAR: Main Features ---
st.sidebar.header("🚗 Car Details")

# cascading dropdowns
unique_makes = sorted(df['Make'].unique())
selected_make = st.sidebar.selectbox("Make (Brand)", unique_makes)

unique_models = sorted(df[df['Make'] == selected_make]['Model'].unique())
selected_model = st.sidebar.selectbox("Model", unique_models)

year = st.sidebar.number_input("Year", min_value=1990, max_value=2026, value=2020)
mileage = st.sidebar.number_input("Mileage (km)", min_value=0, value=50000, step=1000)
condition = st.sidebar.selectbox("Condition", sorted(df['Condition'].astype(str).unique()))

# --- MAIN PAGE: Technical Specs ---
st.title("🤖 Car Price Predictor")
st.markdown("### Technical Specifications")

col1, col2, col3 = st.columns(3)

with col1:
    fuel_type = st.selectbox("Fuel Type", sorted(df['Fuel_Type'].astype(str).unique()))
    transmission = st.selectbox("Transmission", sorted(df['Transmission'].astype(str).unique()))
    drive_type = st.selectbox("Drive Type", sorted(df['Drive_Type'].astype(str).unique()))

with col2:
    engine_vol = st.number_input("Engine Volume (L)", 0.0, 8.0, 2.0)
    horsepower = st.number_input("Horsepower", 50, 1000, 150)
    cylinders = st.selectbox("Cylinders", [4, 6, 8, 12, 'Unknown'])

with col3:
    body_type = st.selectbox("Body Type", sorted(df['Body_Type'].astype(str).unique()))
    color = st.selectbox("Color", sorted(df['Color'].astype(str).unique()))
    steering = st.selectbox("Steering", ["Left", "Right"])

# Advanced / Less Common Features in Expander
with st.expander("Show Advanced Options (Trim, Wheels, EV Info)"):
    c1, c2 = st.columns(2)
    with c1:
        is_taxed = st.radio("Customs Cleared? (Taxed)", ["Yes", "No"])
        trim = st.text_input("Trim / Modification", "Base")
        interior = st.selectbox("Interior Color", sorted(df['Interior_Color'].astype(str).unique()))
    with c2:
        battery = st.number_input("Battery (kWh) - EVs only", 0, 150, 0)
        range_km = st.number_input("Range (km) - EVs only", 0, 1000, 0)
        wheel_size = st.text_input("Wheel Size (e.g., 17)", "17")

# --- PREDICTION LOGIC (FIXED) ---
if st.button("💰 Predict Price"):
    
    # 1. Prepare Input Data 
    # CRITICAL: The order and existence of columns must match X_train exactly.
    # We accidentally missed 'Year' before, which caused the columns to shift.
    input_data = {
        'Make': [selected_make],
        'Model': [selected_model],
        'Taxed': ['1' if is_taxed == "Yes" else '0'], 
        'Year': [year],  # <--- THIS WAS MISSING!
        'Wheel_Size': [str(wheel_size)], # Ensure string if trained as string
        'Color': [color],
        'Door_Count': [4], 
        'Body_Type': [body_type],
        'Range_Km': [float(range_km) if range_km > 0 else -1.0],
        'Horsepower': [float(horsepower)],
        'Steering': [steering],
        'Battery_Capacity': [float(battery) if battery > 0 else -1.0],
        'Cylinders': [float(cylinders) if cylinders != 'Unknown' else -1.0],
        'Trim': [trim],
        'Fuel_Type': [fuel_type],
        'Engine_Volume': [float(engine_vol)],
        'Interior_Color': [interior],
        'Mileage': [float(mileage)],
        'Condition': [condition],
        'Transmission': [transmission],
        'Drive_Type': [drive_type],
        'Electric_Motor_Count': [0], 
        'Car_Age': [2025 - year] 
    }
    
    # Convert to DataFrame
    input_df = pd.DataFrame(input_data)
    
    # 2. Force Column Order
    # To be 100% safe, we force the columns to be in the exact order the model expects.
    # This prevents "Left" from sliding into a numeric slot ever again.
    expected_order = [
        'Make', 'Model', 'Taxed', 'Year', 'Wheel_Size', 'Color', 
        'Door_Count', 'Body_Type', 'Range_Km', 'Horsepower', 'Steering', 
        'Battery_Capacity', 'Cylinders', 'Trim', 'Fuel_Type', 
        'Engine_Volume', 'Interior_Color', 'Mileage', 'Condition', 
        'Transmission', 'Drive_Type', 'Electric_Motor_Count', 'Car_Age'
    ]
    
    # Reorder the dataframe to match training
    input_df = input_df[expected_order]
    
    # 3. Predict
    try:
        log_pred = model.predict(input_df)
        price_pred = np.expm1(log_pred)
        
        st.success(f"## Estimated Price: ${price_pred[0]:,.0f}")
        st.info("💡 Note: This prediction assumes the car is in typical market condition.")
        
    except Exception as e:
        st.error(f"Prediction Failed: {e}")
        st.write("Debug Info - Input Data Types:")
        st.write(input_df.dtypes)