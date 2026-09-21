# Claude Code hafızası (proje notları)

Bu klasör, Claude Code'un bu proje için biriktirdiği kalıcı notların kopyasıdır: çalışma ortamı, kullanıcı
tercihleri, doğrulanmış değerler ve "şu kararı şu yüzden böyle verdik" türü, koddan ya da git geçmişinden
çıkarılamayan bilgiler. `MEMORY.md` dizindir; her satır bir nota işaret eder.

Claude bu notları **repodan değil**, makinedeki şu yoldan okur:

    ~/.claude/projects/<proje-yolunun-slug'ı>/memory/

Slug, projenin tam yolundaki `/` karakterlerinin `-` ile değiştirilmiş hâlidir. Bu Mac'te proje
`~/Desktop/kesifProjesicld` olduğu için slug `-Users-huseyinefkanalp-Desktop-kesifProjesicld`.

## Başka bir makineye taşıma

Repoyu klonladıktan sonra bu klasörün içeriğini o makinedeki karşılığına kopyalayın:

```bash
# macOS / Linux — <kullanıcı> ve klon yolunu kendinize göre değiştirin
SLUG=$(pwd | sed 's:/:-:g')
mkdir -p ~/.claude/projects/$SLUG/memory
cp .claude/memory/*.md ~/.claude/projects/$SLUG/memory/
rm ~/.claude/projects/$SLUG/memory/OKUBENI.md
```

```powershell
# Windows
$slug = (Get-Location).Path -replace '[\\:]', '-'
New-Item -ItemType Directory -Force "$HOME\.claude\projects\$slug\memory" | Out-Null
Copy-Item .claude\memory\*.md "$HOME\.claude\projects\$slug\memory\"
Remove-Item "$HOME\.claude\projects\$slug\memory\OKUBENI.md"
```

## Güncel tutma

Buradaki dosyalar bir **kopyadır**; Claude yeni not yazdığında ya da bir notu güncellediğinde kendi
dizinine yazar, bu klasör kendiliğinden değişmez. Eşitlemek için aynı komutu ters yönde çalıştırın, ya da
canlı dizini bu klasöre bağlayın (tek makinede tek yön seçin):

```bash
SLUG=$(pwd | sed 's:/:-:g')
mv ~/.claude/projects/$SLUG/memory ~/.claude/projects/$SLUG/memory.yedek
ln -s "$(pwd)/.claude/memory" ~/.claude/projects/$SLUG/memory
```

Bağlandıktan sonra Claude'un yazdığı her not doğrudan repoya düşer; commit etmeyi unutmayın.
