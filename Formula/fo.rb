# Homebrew formula for `fo` (file-organizer).
#
# Install via a tap:
#   brew tap aliakpoyraz/fo https://github.com/aliakpoyraz/homebrew-fo
#   brew install fo
#
# Before this works you must:
#   1. Push a public repo and cut a tag, e.g. v0.1.0.
#   2. Set `url` to that tag's tarball and fill in its sha256:
#        curl -sL <tarball-url> | shasum -a 256
#   3. Generate the Python dependency resource stanzas automatically:
#        brew install pipgrip
#        brew update-python-resources Formula/fo.rb
#      (this fills in click, PyYAML, watchdog, questionary and their deps).
#   4. Put this file in a repo named `homebrew-fo`.
class Fo < Formula
  include Language::Python::Virtualenv

  desc "Configurable CLI that sorts files into folders, with one-key undo"
  homepage "https://github.com/aliakpoyraz/file-organizer"
  url "https://github.com/aliakpoyraz/file-organizer/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "REPLACE_WITH_TARBALL_SHA256"
  license "MIT"

  depends_on "python@3.12"

  # `brew update-python-resources Formula/fo.rb` generates the stanzas below.
  # resource "click" do
  #   url "https://files.pythonhosted.org/.../click-8.x.tar.gz"
  #   sha256 "..."
  # end
  # resource "PyYAML" do ... end
  # resource "watchdog" do ... end
  # resource "questionary" do ... end

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Usage", shell_output("#{bin}/file-organizer --help")
    system bin/"forg", "--version"
  end
end
