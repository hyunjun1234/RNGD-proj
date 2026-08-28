#!/usr/bin/env bash
# param_files 캐시에서 '아티팩트에 같은 이름 사본이 있는' 것만 지운다.
#
# 왜 안전한가: 두 곳의 파일은 하드링크가 아니라 각자 전체 사본이다(inode 다름, 링크수 1, 크기 동일).
# 서빙은 아티팩트 폴더에서 읽으므로(serve 로그의 "Loading artifact from path") 캐시를 지워도 안 깨진다.
# 다시 빌드할 때는 캐시가 새로 만들어진다.
#
#   bash clean_param_files.sh          # 무엇을 지울지 보여만 준다
#   bash clean_param_files.sh --yes    # 실제로 지운다
set -uo pipefail
CACHE=/mnt/nvme2n1p1/models/furiosa/llm/param_files
ART=/mnt/nvme2n1p1/models/artifacts
GO=${1:-}

echo "지우기 전 여유:"; df -h /mnt/nvme2n1p1 | tail -1
echo
total=0
for d in "$CACHE"/params-*/; do
  n=$(basename "$d")
  copy=""
  for a in "$ART"/*/; do [ -d "$a$n" ] && copy="$a"; done
  sz=$(du -sm "$d" 2>/dev/null | cut -f1)
  if [ -z "$copy" ]; then
    printf "  건너뜀  %6sM  %s  (사본 없음)\n" "$sz" "${n:0:52}"
    continue
  fi
  # 사본이 실제로 같은 크기인지 한 번 더 본다
  a_sz=$(du -sm "$copy$n" 2>/dev/null | cut -f1)
  if [ "$sz" != "$a_sz" ]; then
    printf "  건너뜀  %6sM  %s  (크기 다름: 캐시 %s / 아티팩트 %s)\n" "$sz" "${n:0:40}" "$sz" "$a_sz"
    continue
  fi
  total=$((total+sz))
  if [ "$GO" = "--yes" ]; then
    rm -rf "$d" && printf "  삭제됨  %6sM  %s  ← %s\n" "$sz" "${n:0:44}" "$(basename "$copy")"
  else
    printf "  삭제대상 %6sM  %s  ← %s\n" "$sz" "${n:0:44}" "$(basename "$copy")"
  fi
done
echo
printf "합계 %.1f GiB\n" "$(echo "scale=1;$total/1024" | bc)"
if [ "$GO" = "--yes" ]; then
  echo "지운 뒤 여유:"; df -h /mnt/nvme2n1p1 | tail -1
  echo
  echo "확인: 아티팩트 서빙이 되는지 한 번 띄워 보세요"
  echo "  curl -s localhost:8400/v1/chat/completions -H 'Content-Type: application/json' \\"
  echo "    -d '{\"model\":\"Qwen3-32B-FP8@tp8\",\"messages\":[{\"role\":\"user\",\"content\":\"안녕\"}],\"max_tokens\":16}'"
else
  echo "실제로 지우려면:  bash clean_param_files.sh --yes"
fi
