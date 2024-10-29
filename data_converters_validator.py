import os
import json
import base64
import time
from tb_rest_client.rest_client_pe import RestClientPE
import re

ENDPOINT = os.getenv("ENDPOINT")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

client = RestClientPE(base_url=ENDPOINT)
client.login(username=USERNAME, password=PASSWORD)


def find_payload_and_result_pairs(directory):
    payloads = sorted([f for f in os.listdir(directory) if re.match(r'payload(_\d+)?\.json', f)])
    results = sorted([f for f in os.listdir(directory) if re.match(r'result(_\d+)?\.json', f)])

    pairs = []

    if 'payload.json' in payloads and 'result_1.json' in results:
        pairs.append(('payload.json', 'result_1.json'))
    elif 'payload.json' in payloads and 'result_1.json' not in results:
        print(f"Validation failed for {directory}: payload.json is present, but result_1.json is missing.")
    elif 'result_1.json' in results and 'payload.json' not in payloads:
        print(f"Validation failed for {directory}: result_1.json is present, but payload.json is missing.")

    for payload_file in payloads:
        if re.match(r'payload_\d+\.json', payload_file):
            suffix = re.search(r'_(\d+)\.json', payload_file).group(1)
            result_file = f"result_{suffix}.json"
            if result_file in results:
                pairs.append((payload_file, result_file))
            else:
                print(f"Validation failed for {directory}: {payload_file} is present, but {result_file} is missing.")

    for result_file in results:
        if re.match(r'result_\d+\.json', result_file):
            suffix = re.search(r'_(\d+)\.json', result_file).group(1)
            payload_file = f"payload_{suffix}.json"
            if payload_file not in payloads:
                print(f"Validation failed for {directory}: {result_file} is present, but {payload_file} is missing.")

    return pairs


def validate_uplink_downlink(directory):
    converter_file = os.path.join(directory, 'converter.json')
    metadata_file = os.path.join(directory, 'metadata.json')

    if not os.path.exists(converter_file):
        print(f"Validation failed for {directory}: converter.json is missing.")
        return False
    if os.path.getsize(converter_file) == 0:
        print(f"Validation failed for {directory}: converter.json is empty.")
        return False

    if not os.path.exists(metadata_file):
        print(f"Validation failed for {directory}: metadata.json is missing.")
        return False
    if os.path.getsize(metadata_file) == 0:
        print(f"Validation failed for {directory}: metadata.json is empty.")
        return False

    with open(converter_file) as f:
        converter = json.load(f)
    with open(metadata_file) as f:
        metadata = json.load(f)

    configuration = converter.get('configuration')
    script_lang = configuration.get('scriptLang')

    request = {
        "metadata": metadata,
    }

    payload_result_pairs = find_payload_and_result_pairs(directory)

    if not payload_result_pairs:
        print(f"Validation failed for {directory}: No valid payload-result pairs found.")
        return False

    success = True

    for payload_file, result_file in payload_result_pairs:
        if not os.path.exists(os.path.join(directory, payload_file)):
            print(f"Validation failed for {directory}: {payload_file} is missing.")
            success = False
            continue
        if os.path.getsize(os.path.join(directory, payload_file)) == 0:
            print(f"Validation failed for {directory}: {payload_file} is empty.")
            success = False
            continue

        if not os.path.exists(os.path.join(directory, result_file)):
            print(f"Validation failed for {directory}: {result_file} is missing.")
            success = False
            continue
        if os.path.getsize(os.path.join(directory, result_file)) == 0:
            print(f"Validation failed for {directory}: {result_file} is empty.")
            success = False
            continue

        with open(os.path.join(directory, payload_file)) as pf:
            payload = json.load(pf)
        with open(os.path.join(directory, result_file)) as rf:
            expected_result = json.load(rf)

        if 'uplink' in directory:
            decoder = configuration.get("decoder") if script_lang == "JS" else configuration.get("tbelDecoder")
            encoded_payload = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')
            request["decoder"] = decoder
            request["payload"] = encoded_payload
            actual_result = client.converter_controller.test_up_link_converter_using_post(
                async_req='false', body=request, script_lang=script_lang)
        elif 'downlink' in directory:
            encoder = configuration.get("encoder") if script_lang == "JS" else configuration.get("tbelEncoder")
            request["encoder"] = encoder
            request["msg"] = json.dumps(payload)
            request["msgType"] = "POST_TELEMETRY_REQUEST"
            request["integrationMetadata"] = {}
            actual_result = client.converter_controller.test_down_link_converter_using_post(
                async_req='false', body=request, script_lang=script_lang)
        else:
            raise ValueError(f"Directory '{directory}' is not recognized as 'uplink' or 'downlink'.")

        result_value = actual_result.get()
        output = result_value.get('output')
        error = result_value.get('error')

        if error != '':
            success = False
            result_message = f"Validation failed for {directory} with payload {payload_file} and result {result_file} with error: {error}\n"
        elif json.loads(output) == expected_result:
            result_message = f"Validation passed for {directory} with payload {payload_file} and result {result_file}\n"
        else:
            success = False
            result_message = f"Validation failed for {directory} with payload {payload_file} and result {result_file}. Expected output does not match.\n"

        print(result_message)

        time.sleep(1)

    return success


def walk_vendors_directory(root_dir):
    all_success = True

    for root, dirs, files in os.walk(root_dir):
        if root.endswith('uplink') or root.endswith('downlink'):
            success = validate_uplink_downlink(root)
            if not success:
                all_success = False

    return all_success


if __name__ == "__main__":
    root_directory = "VENDORS"
    all_success = walk_vendors_directory(root_directory)

    if all_success:
        print("All converters data validated successfully.")
    else:
        exit(1)
