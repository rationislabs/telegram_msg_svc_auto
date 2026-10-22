import sys

if sys.argv[1:2] == ["answer"]:
    from . import answer  # stage 1 never loads the answer bot's dependencies

    sys.exit(answer.main())
if sys.argv[1:2] == ["profile"]:
    from . import answer

    sys.exit(answer.profile())
from . import bot

sys.exit(bot.main(sys.argv[1:]))
