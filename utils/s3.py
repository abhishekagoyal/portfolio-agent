import boto3
import json
import os
from dotenv import load_dotenv

load_dotenv()

BUCKET = os.getenv('S3_BUCKET_NAME', 'market-agent-abhis')

def get_s3_client():
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
    )

def save_positions(positions: list) -> bool:
    try:
        s3 = get_s3_client()
        s3.put_object(
            Bucket=BUCKET,
            Key='portfolio/positions.json',
            Body=json.dumps(positions, indent=2),
            ContentType='application/json'
        )
        print(f'Saved {len(positions)} positions to S3')
        return True
    except Exception as e:
        print(f'S3 save error: {e}')
        return False

def load_positions() -> list:
    try:
        s3 = get_s3_client()
        response = s3.get_object(Bucket=BUCKET, Key='portfolio/positions.json')
        return json.loads(response['Body'].read().decode('utf-8'))
    except s3.exceptions.NoSuchKey:
        return []
    except Exception as e:
        print(f'S3 load error: {e}')
        return []

def save_span_results(results: dict) -> bool:
    try:
        s3 = get_s3_client()
        s3.put_object(
            Bucket=BUCKET,
            Key='portfolio/span_results.json',
            Body=json.dumps(results, indent=2),
            ContentType='application/json'
        )
        return True
    except Exception as e:
        print(f'S3 span save error: {e}')
        return False

def load_span_results() -> dict:
    try:
        s3 = get_s3_client()
        response = s3.get_object(Bucket=BUCKET, Key='portfolio/span_results.json')
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        print(f'S3 span load error: {e}')
        return {}
