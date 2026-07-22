import json
import os
from openai import OpenAI

client = OpenAI(
    api_key="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", 
    base_url="https://api.groq.com/openai/v1"
)

with open("banned_words.json", "r", encoding="utf-8") as file:
    banned_rules = json.load(file)

audio_file_path = "test_call.mp3"


print("Converting audio to text...")
with open(audio_file_path, "rb") as audio_file:
    transcript_response = client.audio.transcriptions.create(
        model="whisper-large-v3", # GROQ model name
        file=audio_file
    )

transcript_text = transcript_response.text
print("\nText:")
print(transcript_text)

prompt = f"""
You are a strict Senior Quality Assurance Auditor. Your job is NOT to coach on politeness or style, but to find STRICT GRAMMATICAL ERRORS ONLY.

Transcript: "{transcript_text}"

Reference Lists:
- English Banned Phrases: {banned_rules.get('english_banned', [])}
- Spanish Banned Phrases: {banned_rules.get('spanish_banned', [])}
- English Offensive Words: {banned_rules.get('english_offensive', [])}
- Spanish Offensive Words: {banned_rules.get('spanish_offensive', [])}

Tasks to execute:
1. Detect primary spoken language (English or Spanish).
2. Check if the agent used ANY exact phrase from the Banned lists provided above. List them in `banned_words_found`. Set `has_profanity` to true if offensive words are found.
3. Check if the agent used ANY exact word from the Offensive lists provided above. List them in `offensive_words_found`.
4. Check for GRAMMAR ERRORS ONLY. 
 - STRICT RULE: Do NOT flag sentences just because they lack politeness, or because you want a "better phrasing" (e.g., "Sorry for bothering" or "When did you leave?" are grammatically correct and MUST NOT be flagged). 
 - Only flag undeniable grammar, tense, or syntax structural breakages (e.g., "He go" instead of "He goes"). 
 - If a sentence is grammatically correct, leave it alone. If there are no true grammar errors, return an empty list [].
5. Write a short executive audit summary paragraph.

Return ONLY a valid JSON object matching this structure precisely:
{{
"language": "English/Spanish",
"has_profanity": true/false,
"offensive_words_found": [],
"banned_words_found": [],
"grammar_errors": [
{{"error": "string", "correction": "string", "reason": "string"}}
],
"audit_summary": "string summary paragraph"
}}
"""
  
response = client.chat.completions.create(
model="llama-3.3-70b-versatile",
response_format={"type": "json_object"},
messages=[{"role": "user", "content": prompt}]
)
  
result = json.loads(response.choices[0].message.content)

# --- 2. معادلة الحساب الآلي للدرجات (Smart Automated Scoring Logic) ---
base_score = 10.0
  
# خصم على الكلمات المسيئة (كل كلمة مسيئة تخصم درجتين مثلاً)
offensive_count = len(result.get("offensive_words_found", []))
base_score -= (offensive_count * 2.0)
  
# خصم على العبارات المحظورة (كل عبارة تخصم درجة واحدة)
banned_count = len(result.get("banned_words_found", []))
base_score -= (banned_count * 1.0)
  
# خصم خفيف جداً وعادل على الأخطاء النحوية (كل خطأ نحوي حقيقي يخصم 0.25 بحد أقصى درجتين مثلاً)
grammar_errors_count = len(result.get("grammar_errors", []))
grammar_penalty = min(grammar_errors_count * 0.25, 2.0)
base_score -= grammar_penalty

# التأكد أن الدرجة لا تقل عن 0 ولا تزيد عن 10
final_score = max(0.0, min(10.0, base_score))
# تقريب الرقم لرقم عشري واحد (مثل 9.5 أو 8.75)
final_score = round(final_score, 2)

# إدراج النتيجة المحسوبة جوه الـ result عشان تظهر في الواجهة
result["score"] = final_score

# --- معادلة الحساب الآلي للدرجات (خصم 0.25 لكل خطأ نحوي) ---
base_score = 10.0

# خصم الكلمات المسيئة
offensive_count = len(result.get("offensive_words_found", []))
base_score -= (offensive_count * 2.0)

# خصم العبارات المحظورة
banned_count = len(result.get("banned_words_found", []))
base_score -= (banned_count * 1.0)

# خصم 0.25 لكل خطأ نحوي حقيقي (بحد أقصى درجتين)
grammar_errors_count = len(result.get("grammar_errors", []))
grammar_penalty = min(grammar_errors_count * 0.25, 2.0)
base_score -= grammar_penalty

# ضبط الدرجة النهائية بين 0 و 10
final_score = max(0.0, min(10.0, base_score))
final_score = round(final_score, 2)

result["score"] = final_score

print("\nAnalyzing and detecting errors...")
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile", 
    response_format={"type": "json_object"},
    messages=[{"role": "user", "content": prompt}]
)

# 4. Print the final report
result = json.loads(response.choices[0].message.content)
print("\n--- Final Report ---")
print(json.dumps(result, indent=2, ensure_ascii=False))