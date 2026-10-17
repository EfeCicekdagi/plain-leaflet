# Prompt iterasyon günlüğü

Her prompt değişikliğinde 3 satır yazılır: ne denendi, ne bozuldu, ne değiştirildi.
Rapordaki "Model, promptlar ve tasarım gerekçeleri" bölümü buradan yazılır. Promptların birebir metni `prompts/` klasöründedir.
Kurs sayfa numaraları Samsung Innovation Campus "Generative AI" ders notlarına aittir (Bölüm 2: Prompt Engineering Basics, Bölüm 3: Foundation Models and Platforms, Bölüm 4: AI Ethics and Responsibility).

## Akış: Draft -> Validate -> Finalize (Bölüm 2, s.82-85)

```
KT metni
  -> [Model 1 / Taslak]     01_kartlar.txt: 5 kart + kanıt alıntıları + eczacı soruları (JSON şeması zorunlu)
  -> [Kod / Kontrol]        her kanıt KT'de geçiyor mu (difflib >= 0.85) + sayılar tutarlı mı
  -> [Model 2 / Kontrol]    02_dogrulayici.txt: her sade cümle 4 kritere göre alıntıyla karşılaştırılır
  -> [Kod / Son hal]        geçemeyen madde silinir ve "desteklenmeyen" listesine yazılır, güven hesaplanır
  -> [İnsan / Son karar]    hasta her maddenin kaynağını görür; belirsizlikler eczacıya soru olarak gider
```

## Teknikler nerede ve neden kullanıldı

| Kurs tekniği | Bizde nerede | Neden |
|---|---|---|
| 6 öğe: Role, Goal, Context, Constraints, Style, Output Format (Bölüm 2, s.40-48) | İki promptta da `[ROL]`, `[GÖREV]`, `[BAĞLAM]`, `[YAPMA LİSTESİ]`, `[STİL]`, `[ÇIKTI BİÇİMİ]` başlıkları | Model tahmin etmesin; her öğe ayrı ve düzenlenebilir olsun. |
| System prompt ve instruction ayrımı (Bölüm 2, s.107-112) | Prompt dosyaları `### SİSTEM` ve `### TALİMAT` olarak ikiye bölünür. Sistem kısmı Gemini'ye `system_instruction` olarak gider. | Her zaman geçerli kurallar (rol, altın kural, yasaklar, stil) görevden ayrı tutulur; kural değişikliği tek yerden yapılır. |
| Domain context (Bölüm 2, s.62-63) | `[BAĞLAM]`: yaşlı hasta, büyük puntolu ekran, "Kaynağı göster" düğmesi, ikinci denetçi | Model çıktının nerede, kime gösterileceğini ve kanıtın neden birebir olması gerektiğini bilir. |
| Negative prompting: Form / Content / Behavior (Bölüm 2, s.64-68) | `[YAPMA LİSTESİ]` İçerik / Davranış / Biçim olarak üçe bölündü. Doz uydurma, teşhis, korkutucu dil ve tahmin yasak. | Kursun belirttiği gibi "Don't" olmadan model tahmin eder ve fazla yazar. Korkutucu dil yasağı yaşlı kullanıcı için eklendi (s.67). |
| Style control (Bölüm 2, s.114-116) | `[STİL]`: en fazla 12 kelime, tek bilgi, günlük kelime, "siz" hitabı | İçerik doğru olsa bile yanlış seviyedeki dil yaşlı kullanıcı için işe yaramaz. Ateşman skoru bunu ölçer. |
| Zero-shot | Kurallar + şema (örnek olmadan da çalışır) | Temel davranış. |
| Few-shot, örnek + kural, "örneği kopyalama" (Bölüm 2, s.96, s.103-104) | `01_kartlar.txt [ÖRNEKLER]`: 2 doğru + 1 YANLIŞ örnek. `02_dogrulayici.txt`: 1 onay + 2 ret örneği | Sade dilin seviyesini ve kanıtın nasıl kopyalanacağını gösterir. Yanlış örnek en sık hatayı (kanıtı özetlemek, bilgi eklemek) öğretir. "Örneklerdeki bilgileri kullanma" kuralı örnek sızmasını önler. |
| Step-by-step / Chain-of-thought (Bölüm 2, s.146-148) | `[ADIMLAR]` 1-6, ara sonuçlar `analiz` alanına yazılır (uyarılar, belirsiz noktalar). Doğrulayıcıda önce `neden`, sonra karar. | "Hemen doktora" kartı ve eczacı soruları, model önce tüm uyarıları listelediğinde daha eksiksiz olur. `analiz` alanı arayüze gitmez. |
| Tree of Thoughts (Bölüm 2, s.149-153) | Adım 4: eczacı soruları için 5 farklı eksende aday üretilir (`soru_adaylari`), her biri `onem` ile değerlendirilir, en iyi 5 seçilir. | Eczacı sorularında tek doğru cevap yoktur, seçim yapılır. Kursun dediği gibi ToT "seçim" gereken yerde işe yarar. Eksenler önceden verildiği için sorular tek konuda toplanmaz (diversity, s.151). |
| Verification: self-check (Bölüm 2, s.69-71) | Adım 6: 4 maddelik geçti/kaldı listesi | Model çıktıyı vermeden önce kendi maddelerini kontrol eder. |
| Verification: criteria-based review (Bölüm 2, s.72) | `02_dogrulayici.txt` 4 ölçülebilir kriter: `k1_ek_bilgi_yok`, `k2_anlam_ayni`, `k3_kosul_korunmus`, `k4_sayilar_ayni` | "İyi mi?" yerine evet/hayır kriterleri. Karar kodda verilir: 4 kriterin hepsi evet değilse model "destekleniyor" dese bile madde silinir. Hangi kriterin ne kadar ret verdiği `results.md`'ye yazılır. |
| Verification: source/evidence request (Bölüm 2, s.73) | Her maddede zorunlu `kanit` alanı | Her cümle talimattan bir alıntıya bağlanır; hasta "Kaynağı göster" ile kontrol eder. |
| Schema-first prompting, validate -> repair -> re-validate (Bölüm 2, s.117-120) | `core/schema.py` içindeki `KART_CEVAP_SEMASI` ve `DOGRULAYICI_CEVAP_SEMASI` Gemini'ye `response_schema` olarak verilir (alan sırası, zorunlu alanlar, enum, en fazla 5 madde). Cevap JSON değilse bir kez onarma isteğiyle tekrar sorulur. Sonra `schema.normalize()` sözleşmeye uydurur. | Kursun uyardığı gibi "schema ≠ truth": doğru biçim yanlış içerik taşıyabilir. Bu yüzden şemanın üstüne kanıt, sayı ve LLM kontrolleri eklendi. |
| Prompt injection önlemi: öncelik, sınır ayırma, engelleme (Bölüm 2, s.161-168) | `[KURAL ÖNCELİĞİ]` Sistem > Görev > Belge. Belge `<kullanma_talimati>` etiketleri içinde, belgenin içindeki aynı etiketler kodla silinir (`_veri_temizle`). KT olmayan metin için `kt_mi: false` + `red_nedeni`, kullanıcıya tek cümle neden + güvenli alternatif gösterilir (refusal pattern, s.167). | KT metni dışarıdan gelen, güvenilmeyen belgedir. |
| Template reuse (Bölüm 2, s.124-126) | Prompt dosyaları sabit; sadece `{kt_metni}` ve `{maddeler}` değişkenleri doldurulur. | Kurallar kodun içine dağılmaz, rapordaki prompt ile koddaki prompt aynıdır. |
| Greedy decoding / düşük sıcaklık (Bölüm 3, s.65-67) | `config.TEMPERATURE = 0` | Tıbbi metinde yaratıcılık değil tutarlılık istenir; aynı KT her seferinde aynı sonucu verir. |
| Grounding (Bölüm 3, s.68) | Altın kural: sadece verilen KT kullanılır. | Model "olasılıksal metin tamamlayıcıdır, doğrulayıcı değildir"; cevap belgeye bağlanmalı. |
| Hybrid LLM + SLM (Bölüm 2, s.25-26) | İsteğe bağlı: `GEMINI_DOGRULAYICI_MODEL=gemini-2.5-flash-lite` ile doğrulayıcı daha küçük modelle çalışabilir. | Doğrulayıcı bir sınıflandırma işidir. Varsayılan olarak ikisi de aynı model; küçük modelin sonucu ölçülmeden açılmaz. |

## Etik: katmanlı koruma (Bölüm 4)

| Katman (Bölüm 4, s.119) | Bizde |
|---|---|
| Input rail | Belge veri olarak etiketlenir, gömülü talimatlar yok sayılır, KT olmayan metin reddedilir, çok kısa metin modele gitmez. |
| Dialog rail | Teşhis yok, kişiye özel doz yok, "ilacı bırakın" yok, korkutucu dil yok (sistem promptu). |
| Output rail | JSON şeması + kanıt KT'de mi (difflib) + sayılar tutarlı mı (kod) + LLM doğrulayıcı (4 kriter). Doğrulanamayan madde silinir ("If you cannot verify it, remove it", s.53). |
| İnsan denetimi | Her madde kaynağıyla gösterilir, güven düşükse sarı uyarı çıkar, belirsizlikler eczacıya soru olarak verilir. |

Ölçüt: halüsinasyon oranı %5'in altı (Bölüm 4, s.104-105). `eval/results.md` hem doğrulayıcıdan önceki hem sonraki oranı verir.
Hedef kullanıcı neden önemli: "Older adults and digitally marginalized groups face higher risk" (Bölüm 4, s.49).

## Günlük

### v1 - ilk sürüm (Cmt)
- **Ne denendi:** Ana dokümandaki Prompt 1 iskeleti + 3 few-shot + `analiz` alanında CoT + `kt_mi`. Doğrulayıcı tek soruyla ("fazlasını söylüyor mu?") evet/hayır veriyordu.
- **Ne bozuldu:** Gerçek modelle denenmedi. Kod incelemesinde iki açık bulundu: (1) Model few-shot örneklerindeki saklama cümlesini kanıt olarak kopyalayabilirdi. (2) Kanıttaki bir sayı değişirse (örn. "65 yaş" -> "75 yaş") difflib benzerliği 0.99 kalıyor ve madde geçiyordu; LLM doğrulayıcı da cümleyi bozuk kanıtla karşılaştırdığı için yakalayamıyordu.
- **Ne değiştirildi:** v2'ye geçildi.

### v2 - kurs yapısına göre yeniden yazım (Cmt)
- **Ne denendi:** Promptlar sistem/talimat olarak ikiye bölündü, 6 öğe başlıkları eklendi. Negative prompting üç alana ayrıldı. Few-shot'a bir YANLIŞ örnek, eczacı sorularına ToT, öz kontrol listesi, Gemini `response_schema` eklendi. Doğrulayıcı 4 kriterli hale getirildi, karar koda alındı. Kod tarafına sayı tutarlılık kontrolü eklendi.
- **Ne bozuldu:** _(gerçek KT ile ilk denemeden sonra doldurulacak)_
- **Ne değiştirildi:** _(...)_
