from transformers import AutoTokenizer, AutoConfig, AutoModelForMultipleChoice
from flask import Flask, request, jsonify, render_template
from queue import Queue, Empty
from threading import Thread
import time
import torch

app = Flask(__name__)

print("model loading...")

# Model loading

model_name = "ehdwns1516/bert-base-uncased_SWAG"
tokenizer = AutoTokenizer.from_pretrained(model_name)
config = AutoConfig.from_pretrained(model_name)
model = AutoModelForMultipleChoice.from_pretrained(model_name, config=config)

requests_queue = Queue()    # request queue.
BATCH_SIZE = 1              # max request size.
CHECK_INTERVAL = 0.1

print("complete model loading")

def run_model(candicates_num, question: str, candicates: list[str]):
    assert len(candicates) == candicates_num, "you need " + candicates_num + " candidates"
    choices_inputs = []
    for c in candicates:
        text_a = ""  # empty context
        text_b = question + " " + c
        inputs = tokenizer(
            text_a,
            text_b,
            add_special_tokens=True,
            max_length=128,
            padding="max_length",
            truncation=True,
            return_overflowing_tokens=True,
        )
        choices_inputs.append(inputs)

    input_ids = torch.LongTensor([x["input_ids"] for x in choices_inputs])
    output = model(input_ids=input_ids)

    return {"result": candicates[torch.argmax(output.logits).item()]}

def handle_requests_by_batch():
    while True:
        request_batch = []

        while not (len(request_batch) >= BATCH_SIZE):
            try:
                request_batch.append(requests_queue.get(timeout=CHECK_INTERVAL))
            except Empty:
                continue

            for requests in request_batch:
                try:
                    requests["output"] = run_model(requests['input'][0], requests['input'][1], requests['input'][2])

                except Exception as e:
                    requests["output"] = e


handler = Thread(target=handle_requests_by_batch).start()


@app.route('/generate', methods=['POST'])
def generate():
    if requests_queue.qsize() > BATCH_SIZE:
        return jsonify({'Error': 'Too Many Requests'}), 429

    try:
        args = []
        items = list()

        context = request.form['context']
        count = request.form['count']
        for i in range(int(count)):
            items.append(request.form['items' + '[' + str(i) + ']'])

        args.append(int(count))
        args.append(context)
        args.append(items)
        
        
    except Exception as e:
        return jsonify({'message': 'Invalid request'}), 500

    req = {'input': args}
    requests_queue.put(req)

    while 'output' not in req:
        time.sleep(CHECK_INTERVAL)

    return req['output']


@app.route('/queue_clear')
def queue_clear():
    while not requests_queue.empty():
        requests_queue.get()

    return "Clear", 200


@app.route('/healthz', methods=["GET"])
def health_check():
    return "Health", 200


@app.route('/')
def main():
    return render_template('index.html'), 200


if __name__ == '__main__':
    app.run(port=5000, host='0.0.0.0')