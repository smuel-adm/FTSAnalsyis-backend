from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import pandas as pd
import matplotlib.pyplot as plt
import io, os
import logging
import numpy as np

logging.basicConfig(filename='api_log.txt',level=logging.DEBUG)
logging.debug("API scrpit started")
app = FastAPI()
latest_output_path = None

app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return JSONResponse(status_code= 200, content={"message": "server is working"})

def find_failed_tests(row, benchmarks):
    failed_tests = []
    for col in benchmarks.columns[2:]:
        if pd.notna(row[col]):
            max_value = pd.to_numeric(benchmarks.loc['Upper li', col], errors='coerce')
            min_value = pd.to_numeric(benchmarks.loc['Lower li', col], errors='coerce')
            test_value = pd.to_numeric(row[col], errors='coerce')
            if pd.notna(test_value) and (test_value > max_value or test_value < min_value):
                failed_tests.append(col)
    return failed_tests

@app.post("/analyse")
async def analyse_file(file: UploadFile = File(...)):
    global latest_output_path
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    if not file.filename.endswith('.xlsx'):
        raise HTTPException(status_code=400, detail="Please select a .xlsx file")
    
    try:
        content = await file.read()
        df = pd.read_excel(io.BytesIO(content), header=0)
        
        df['Product Code'] = df['File name'].str[:8]
        df.set_index('Product Code', inplace=True)
        
        benchmarks = df.iloc[:8]
        data = df.iloc[8:]
        
        data.replace([np.inf, -np.inf], np.nan, inplace= True)
        data.fillna(0,inplace=True)
        benchmarks.replace([np.inf,-np.inf], np.nan,inplace=True)
        benchmarks.fillna(0, inplace=True)
        
        #filtering ng products
        ng_products = data[data['Judgement'] == 'NG']
        ng_products['Failed Tests'] = ng_products.apply(lambda row: find_failed_tests(row, benchmarks), axis=1)
        
        test_failures = []
        for test in ng_products['Failed Tests'].explode().unique():
            failed_products = ng_products[ng_products['Failed Tests'].apply(lambda tests: test in tests)]
            
            products = []
            for product_code, product_data in failed_products.groupby("Product Code"):
                failure_count = product_data['Failed Tests'].apply(lambda x:x.count(test)).sum()
                products.append({"product_code":product_code,"failures": int(failure_count)})
                
            test_failures.append({
                "test_name":test,
                "total_failures":int(len(failed_products)),
                "products":products
            })
            
            top_failures = sorted(test_failures, key=lambda x:x['total_failures'],reverse=True)[:15]
            
        return JSONResponse(content={"tests":top_failures})
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/plot")
async def get_plot():
    global latest_output_path
    if latest_output_path:
        return FileResponse(latest_output_path)
    else:
        raise HTTPException(status_code=404,detail="No plot availabe yet")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
